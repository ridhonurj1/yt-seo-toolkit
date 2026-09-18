"""CLI yt-seo-toolkit.

Perintah offline (tanpa OAuth):
  audit    <video_url|video_id>            — audit metadata dari video publik (API key mode)
  chapters <file.txt>                      — validasi blok chapters
  thumb    <image.jpg>                     — audit thumbnail
  abtest   <a.jpg> <b.jpg> "judul video"   — plan A/B thumbnail

Perintah OAuth (butuh client secrets):
  auth                                     — jalankan flow OAuth sekali
  list                                     — list video channel sendiri
  optimize <video_id> [--title ...] [--desc-file ...] [--tags ...]
  thumb-set <video_id> <image.jpg>
  research "<query>"                       — lihat pola title/tag kompetitor
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .rules import (
    audit_title,
    audit_tags,
    build_description,
    description_snippet,
    suggest_tags_from_title_and_desc,
    tags_total_length,
)
from .chapters import parse_chapters, validate_block
from .thumbnail import audit_thumbnail


def _extract_video_id(s: str) -> str:
    s = s.strip()
    if "youtu" in s:
        for sep in ("v=", "/shorts/", "youtu.be/", "/embed/"):
            if sep in s:
                tail = s.split(sep, 1)[1]
                vid = tail.split("&")[0].split("?")[0].split("/")[0]
                if vid:
                    return vid
        raise SystemExit(f"tidak bisa mengekstrak video id dari {s!r}")
    return s


def _get_api_key_client():
    key = os.environ.get("YT_API_KEY")
    if not key:
        print("❌ Set YT_API_KEY (Google Cloud > API key, YouTube Data API v3 enabled)", file=sys.stderr)
        sys.exit(2)
    from googleapiclient.discovery import build
    return build("youtube", "v3", developerKey=key)


def cmd_audit(args) -> None:
    vid = _extract_video_id(args.video)
    yt = _get_api_key_client()
    resp = yt.videos().list(part="snippet,statistics,contentDetails", id=vid).execute()
    items = resp.get("items", [])
    if not items:
        print(f"❌ video {vid} tidak ditemukan / private", file=sys.stderr)
        sys.exit(1)
    sn, st = items[0]["snippet"], items[0].get("statistics", {})

    print(f"🎬 {sn.get('title')}")
    print(f"   channel : {sn.get('channelTitle')}")
    print(f"   views   : {st.get('viewCount', '0')}  likes: {st.get('likeCount', '0')}")
    print(f"   duration: {items[0]['contentDetails'].get('duration')}")

    title_audit = audit_title(sn.get("title", ""))
    print("\n── TITLE AUDIT ──")
    if title_audit.ok:
        print("   ✅ aman")
    for i in title_audit.issues:
        print(f"   ⚠️  {i}")
    for s in title_audit.suggestions:
        print(f"   💡 {s}")

    desc = sn.get("description", "")
    snippet = description_snippet(desc)
    tags = sn.get("tags", []) or []
    tag_issues, tag_clean = audit_tags(tags)

    print("\n── DESCRIPTION ──")
    print(f"   panjang : {len(desc)} char (snippet search: {len(snippet)} char)")
    print(f"   snippet : {snippet!r}")
    if "#hashtag" not in desc and desc.count("#") > 15:
        print("   ⚠️  >15 hashtag — YouTube mengabaikan semuanya")

    print("\n── TAGS ──")
    if tags:
        print(f"   jumlah: {len(tags)}  total: {tags_total_length(tags)}/500 char")
        for i in tag_issues:
            print(f"   ⚠️  {i}")
        print(f"   tags: {', '.join(tag_clean[:15])}")
    else:
        print("   ⚠️  tidak ada tags — peluang SEO hilang")
        sugg = suggest_tags_from_title_and_desc(sn.get("title", ""), desc)
        print(f"   💡 sarankan: {', '.join(sugg[:12])}")

    print("\n── CHAPTERS ──")
    if "0:00" in desc or "00:00" in desc:
        errors = [e for line in desc.splitlines() for e in _chapter_line_errors(line)]
        print("   ✅ ada blok chapters" if not errors else f"   ⚠️  {errors}")
    else:
        print("   💡 belum ada chapters — aktif di >60s video, naikkan watch time")


def _chapter_line_errors(line: str):
    from .chapters import parse_chapters
    _, errs = parse_chapters(line)
    return errs


def cmd_chapters(args) -> None:
    text = Path(args.file).read_text(encoding="utf-8")
    chapters, errors = parse_chapters(text)
    if errors:
        for e in errors:
            print(f"❌ {e}", file=sys.stderr)
        sys.exit(1)
    print(f"✅ {len(chapters)} chapters valid:")
    for c in chapters:
        print(f"   {c.stamp}  {c.title}")


def cmd_thumb(args) -> None:
    data = Path(args.image).read_bytes()
    a = audit_thumbnail(data)
    print(f"🖼  {args.image}")
    print(f"   size    : {a.width}x{a.height} (rasio {a.aspect:.2f})")
    print(f"   file    : {a.file_size/1024:.0f}KB")
    print(f"   luma    : mean {a.brightness} / stddev {a.contrast}")
    print(f"   SCORE   : {a.score}/100")
    for i in a.issues:
        print(f"   ⚠️  {i}")
    for n in a.notes:
        print(f"   ✅ {n}")


def cmd_abtest(args) -> None:
    from .thumbnail import plan_ab_test
    plan = plan_ab_test(args.thumb_a, args.thumb_b, args.title)
    print(json.dumps(plan, indent=2, ensure_ascii=False))


def cmd_auth(args) -> None:
    svc = _get_oauth_client(headless=args.headless)
    ch = svc.channels().list(part="snippet", mine=True).execute()
    items = ch.get("items", [])
    if items:
        print(f"✅ terautentikasi sebagai: {items[0]['snippet']['title']}")


def _get_oauth_client(headless: bool = False):
    from .client import get_authenticated_service
    return get_authenticated_service(headless=headless)


def cmd_list(args) -> None:
    from .client import list_my_videos
    yt = _get_oauth_client()
    vids = list_my_videos(yt, max_results=args.limit)
    print(f"{len(vids)} video:")
    for v in vids:
        sn, st = v["snippet"], v.get("statistics", {})
        print(f"   {v['id']}  {sn.get('title','')[:60]:60}  views={st.get('viewCount','0'):>10}")


def cmd_optimize(args) -> None:
    from .client import update_metadata, get_video
    yt = _get_oauth_client()

    before = get_video(yt, args.video_id)
    old = before["snippet"]

    title = args.title
    description = Path(args.desc_file).read_text(encoding="utf-8") if args.desc_file else None
    tags = [t.strip() for t in args.tags.split(",") if t.strip()] if args.tags else None

    if args.suggest_tags and old:
        base = suggest_tags_from_title_and_desc(
            title or old.get("title", ""), description or old.get("description", ""),
            extra=tags or [],
        )
        tags = base
        print(f"💡 tags dihasilkan ({len(tags)}): {', '.join(tags[:15])}")

    resp = update_metadata(
        yt, args.video_id, title=title, description=description, tags=tags,
        category_id=args.category,
    )
    sn = resp["snippet"]
    print("✅ metadata ter-update:")
    print(f"   title  : {sn.get('title')}")
    print(f"   desc   : {len(sn.get('description',''))} char")
    print(f"   tags   : {len(sn.get('tags', []))} tag ({tags_total_length(sn.get('tags', []))}/500)")


def cmd_thumb_set(args) -> None:
    from .client import set_thumbnail
    yt = _get_oauth_client()
    resp = set_thumbnail(yt, args.video_id, args.image)
    print(f"✅ thumbnail di-set: {json.dumps(resp)[:120]}")


def cmd_research(args) -> None:
    from .client import keyword_research
    yt = _get_oauth_client()
    rows = keyword_research(yt, args.query, region=args.region)
    print(f"Top {len(rows)} untuk {args.query!r}:")
    for r in rows:
        print(f"   {r['views']:>10,} views  {r['title'][:58]:58}  [{r['channel']}]")
        if r["tags"]:
            print(f"              tags: {', '.join(r['tags'][:8])}")


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="ytseo", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("audit", help="audit metadata video publik")
    s.add_argument("video")
    s.set_defaults(fn=cmd_audit)

    s = sub.add_parser("chapters", help="validasi file chapters")
    s.add_argument("file")
    s.set_defaults(fn=cmd_chapters)

    s = sub.add_parser("thumb", help="audit thumbnail")
    s.add_argument("image")
    s.set_defaults(fn=cmd_thumb)

    s = sub.add_parser("abtest", help="plan A/B thumbnail")
    s.add_argument("thumb_a")
    s.add_argument("thumb_b")
    s.add_argument("title")
    s.set_defaults(fn=cmd_abtest)

    s = sub.add_parser("auth", help="OAuth flow sekali")
    s.add_argument("--headless", action="store_true")
    s.set_defaults(fn=cmd_auth)

    s = sub.add_parser("list", help="list video channel sendiri")
    s.add_argument("--limit", type=int, default=50)
    s.set_defaults(fn=cmd_list)

    s = sub.add_parser("optimize", help="update metadata video")
    s.add_argument("video_id")
    s.add_argument("--title")
    s.add_argument("--desc-file")
    s.add_argument("--tags", help="koma-pisah")
    s.add_argument("--suggest-tags", action="store_true", help="auto-generate tags")
    s.add_argument("--category", default="22")
    s.set_defaults(fn=cmd_optimize)

    s = sub.add_parser("thumb-set", help="upload thumbnail")
    s.add_argument("video_id")
    s.add_argument("image")
    s.set_defaults(fn=cmd_thumb_set)

    s = sub.add_parser("research", help="riset keyword kompetitor")
    s.add_argument("query")
    s.add_argument("--region", default="ID")
    s.set_defaults(fn=cmd_research)

    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
