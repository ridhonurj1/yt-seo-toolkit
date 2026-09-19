"""ytseo-sync: sinkronisasi clip youtube-clipper-v3 -> YouTube (Rizz.snipbit).

Menghubungkan data clip (SQLite v3) dengan tool SEO:
  * title        -> audit + perbaikan (<=70 char)
  * description  -> builder (snippet hook 150 char + chapters dari transcript)
  * tags         -> generator dari title + transcript + brand
  * thumbnail    -> frame-pick dari rendered video (frame terbaik by score) + hook teks
  * publish      -> videos.update + thumbnails.set via OAuth tersimpan

Pemakaian:
  python -m ytseo.sync --list                     # daftar clip siap sync
  python -m ytseo.sync --plan <clip_id>           # tampilkan hasil yang AKAN di-publish
  python -m ytseo.sync --apply <clip_id> <video_id> [--with-thumb]   # publish nyata
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

V3_DB = Path("/home/kaiden/projects/youtube-clipper-v3/data/db/clipper.db")
FFMPEG = "/home/kaiden/projects/youtube-clipper-v3/node_modules/ffmpeg-static/ffmpeg"

sys.path.insert(0, str(Path(__file__).parent.parent))
from ytseo.rules import (  # noqa: E402
    audit_title, build_description, description_snippet,
    suggest_tags_from_title_and_desc, normalize_tags,
)
from ytseo.thumbnail import audit_thumbnail  # noqa: E402
from ytseo.chapters import validate_block  # noqa: E402

BRAND_TAGS = ["rizz snipbit", "podcast indonesia", "viral indonesia", "klip podcast"]


def load_clip(clip_id: str) -> dict:
    c = sqlite3.connect(f"file:{V3_DB}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    r = c.execute("select * from clips where id = ?", (clip_id,)).fetchone()
    c.close()
    if not r:
        raise SystemExit(f"clip {clip_id} tidak ada di {V3_DB}")
    return dict(r)


def list_syncable() -> list:
    c = sqlite3.connect(f"file:{V3_DB}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    rows = c.execute(
        "select id, project_id, idx, title, status, video_path from clips "
        "where status='completed' and video_path is not null order by created_at desc"
    ).fetchall()
    c.close()
    return [dict(r) for r in rows]


def _transcript_text(clip: dict) -> str:
    try:
        cues = json.loads(clip.get("transcript_json") or "[]")
        return " ".join(x.get("text", "") for x in cues)
    except Exception:
        return ""


def _cue_list(clip: dict) -> list:
    try:
        return json.loads(clip.get("transcript_json") or "[]")
    except Exception:
        return []


def best_frame(video_path: str, workdir: str | None = None) -> tuple[str, dict]:
    """Scan 8 frame merata dari video rendered, pilih skor tertinggi."""
    p = Path(video_path)
    if not p.is_absolute():
        p = Path("/home/kaiden/projects/youtube-clipper-v3") / p
    if not p.exists():
        raise SystemExit(f"video tidak ada: {p}")

    tmp = Path(workdir or tempfile.mkdtemp(prefix="ytseo_frames_"))
    candidates = []
    for i in range(8):
        ss = (i + 1) * 4
        out = tmp / f"frame_{i}.jpg"
        subprocess.run(
            [FFMPEG, "-y", "-ss", str(ss), "-i", str(p), "-frames:v", "1", "-q:v", "2", str(out)],
            capture_output=True,
        )
        if out.exists():
            try:
                a = audit_thumbnail(out.read_bytes())
                candidates.append((a.score, a.brightness, str(out)))
            except Exception:
                continue
    if not candidates:
        raise SystemExit("tidak ada frame terextract")
    candidates.sort(key=lambda r: (-r[0], -r[1]))
    return candidates[0][2], {"score": candidates[0][0], "luma": candidates[0][1], "scanned": len(candidates)}


def build_hook_text(title: str) -> str:
    """Hook 2 baris dari title: maks 14 char per baris, huruf besar."""
    words = re.sub(r"[#@\w]+$", "", title).strip().upper().split()
    lines, cur = [], ""
    for w in words:
        if len(cur) + len(w) + 1 > 14:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
        if len(lines) == 2:
            break
    if cur and len(lines) < 2:
        lines.append(cur)
    return "\n".join(lines[:2])


def plan_sync(clip: dict) -> dict:
    """Susun metadata final tanpa menyentuh YouTube."""
    title = clip["title"] or ""
    ta = audit_title(title)
    if len(title) > 70:
        title = title[:70].rstrip()

    transcript = _transcript_text(clip)
    tags = suggest_tags_from_title_and_desc(title, transcript, extra=list(BRAND_TAGS))

    # chapters dari transcript cues (3 titik: 0 / tengah / akhir-5s)
    dur = float(clip.get("duration") or 0)
    chapters = None
    if dur >= 60:
        mid, last = int(dur // 2), max(10, int(dur - 5))
        block = f"00:00 Pembuka\n{mid//60:02d}:{mid%60:02d} Konten\n{last//60:02d}:{last%60:02d} Penutup"
        if not validate_block(block):
            chapters = block

    hook = (clip.get("hook") or "").strip()
    snippet_src = hook if len(hook) >= 40 else title
    desc = build_description(
        hook=snippet_src,
        body_lines=[f"Klip dari podcast Rizz.snipbit. Subscribe untuk klip baru tiap hari!"],
        hashtags=["podcastindonesia", "rizzsnipbit"],
        chapters=chapters,
    )

    return {
        "clip_id": clip["id"],
        "clip_title": clip["title"],
        "final_title": title,
        "title_issues": ta.issues,
        "final_tags": tags,
        "final_description": desc,
        "snippet": description_snippet(desc),
        "chapters": chapters,
        "video_path": clip["video_path"],
    }


def apply_sync(plan: dict, youtube_video_id: str, with_thumb: bool = True, service=None) -> dict:
    from ytseo.client import get_authenticated_service, update_metadata, set_thumbnail
    yt = service or get_authenticated_service()

    resp = update_metadata(
        yt, youtube_video_id,
        title=plan["final_title"],
        description=plan["final_description"],
        tags=plan["final_tags"],
    )
    thumb_result = None
    if with_thumb:
        frame, info = best_frame(plan["video_path"])
        # gambar hook teks di frame terbaik
        from PIL import Image, ImageEnhance, ImageDraw, ImageFont
        img = Image.open(frame).convert("RGB").resize((1280, 720), Image.LANCZOS)
        img = ImageEnhance.Brightness(img).enhance(1.15)
        img = ImageEnhance.Contrast(img).enhance(1.1)
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf", 84)
        except Exception:
            font = ImageFont.load_default()
        x, y = 40, 40
        for line in build_hook_text(plan["final_title"]).splitlines():
            b = draw.textbbox((x, y), line, font=font)
            draw.rectangle([b[0] - 14, b[1] - 10, b[2] + 14, b[3] + 10], fill=(255, 214, 0))
            draw.text((x, y), line, font=font, fill=(15, 15, 15))
            y += 104
        out = Path(tempfile.mkdtemp(prefix="ytseo_thumb_")) / "thumb.jpg"
        img.save(out, "JPEG", quality=90)
        thumb_result = {"frame_scan": info, "upload": set_thumbnail(yt, youtube_video_id, str(out))}

    return {"metadata": {"id": resp.get("id"), "title": resp["snippet"]["title"]}, "thumbnail": thumb_result}


def main() -> None:
    ap = argparse.ArgumentParser(prog="ytseo-sync")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--plan", metavar="CLIP_ID")
    ap.add_argument("--apply", nargs=2, metavar=("CLIP_ID", "VIDEO_ID"))
    ap.add_argument("--with-thumb", action="store_true", default=True)
    ap.add_argument("--no-thumb", dest="with_thumb", action="store_false")
    args = ap.parse_args()

    if args.list:
        for r in list_syncable():
            print(f"{r['id']}  proj={r['project_id'][:8]}  #{r['idx']}  [{r['status']}]  {r['title'][:60]}")
    elif args.plan:
        plan = plan_sync(load_clip(args.plan))
        print(json.dumps(plan, ensure_ascii=False, indent=1))
    elif args.apply:
        clip_id, video_id = args.apply
        plan = plan_sync(load_clip(clip_id))
        result = apply_sync(plan, video_id, with_thumb=args.with_thumb)
        print(json.dumps(result, ensure_ascii=False, indent=1))
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
