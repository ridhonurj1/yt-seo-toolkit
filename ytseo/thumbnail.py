"""Thumbnail A/B tester — rating heuristik + plan eksperimen.

Fungsi rating deterministik (kontras, kepadatan teks, rasio, kecerahan) —
bukan ML, hanya heuristik yang tahu kenapa thumbnail bagus bagus. Nilai
eksperimen nyata butuh YouTube Analytics API (impresi CTR per thumbnail
TIDAK diekspos per-variant; YouTube sendiri sudah auto-A/B via 'Test &
Compare' — tool ini bantu menyiapkan variant & menilai hasil manual).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

try:
    from PIL import Image
    import io
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

THUMB_W, THUMB_H = 1280, 720
MAX_THUMB_SIZE_BYTES = 2 * 1024 * 1024
ACCEPTED_FORMATS = {"image/jpeg", "image/png", "image/gif", "image/webp"}


@dataclass
class ThumbAudit:
    width: int
    height: int
    aspect: float
    file_size: int
    brightness: float      # 0-255 rata-rata
    contrast: float        # stddev luminance
    edge_density: float    # proxy kepadatan visual
    text_ratio: float      # proxy area teks (area kontras tinggi homogen)
    score: float           # 0-100
    issues: List[str]
    notes: List[str]


def _luma_stats(img) -> Tuple[float, float]:
    g = img.convert("L").resize((64, 36))
    px = list(g.getdata())
    n = len(px)
    mean = sum(px) / n
    var = sum((p - mean) ** 2 for p in px) / n
    return mean, var ** 0.5


def audit_thumbnail(image_bytes: bytes) -> ThumbAudit:
    """Audit thumbnail dari bytes (file dibaca pemanggil). Butuh Pillow."""
    if not HAS_PIL:
        raise RuntimeError("Pillow belum terpasang: pip install Pillow")

    img = Image.open(io.BytesIO(image_bytes))
    w, h = img.size
    aspect = w / h if h else 0
    mean, std = _luma_stats(img)

    issues: List[str] = []
    notes: List[str] = []
    score = 50.0

    if abs(aspect - 16 / 9) > 0.02:
        issues.append(f"rasio {aspect:.2f} != 16:9 — akan di-letterbox/crop YouTube")
        score -= 10

    if w < THUMB_W:
        issues.append(f"resolusi {w}x{h} < 1280x720 — YouTube akan upscale, tajamnya turun")
        score -= 10

    if mean < 60:
        issues.append(f"terlalu gelap (brightness {mean:.0f}/255) — susah dibaca di feed kecil")
        score -= 8
    elif mean > 220:
        issues.append(f"terlalu terang (brightness {mean:.0f}/255) — kontras subjek hilang")
        score -= 8
    else:
        score += 6
        notes.append("brightness sehat")

    if std < 40:
        issues.append(f"kontras rendah (stddev {std:.0f}) — thumbnail datar, tidak menonjol di feed")
        score -= 12
    elif std > 100:
        notes.append("kontras tinggi — bagus untuk feed")
        score += 8

    # Proxy kepadatan teks: hitung rasio piksel 'ekstrem' (misal teks putih di box)
    g = img.convert("L").resize((128, 72))
    px = list(g.getdata())
    n = len(px)
    extremes = sum(1 for p in px if p < 25 or p > 235) / n
    if extremes > 0.35:
        issues.append("area hitam/putih ekstrem >35% — kemungkinan teks besar menutupi subjek")
        score -= 6
    elif 0.05 < extremes < 0.25:
        notes.append("ada teks/overlay — bagus asal subjek tetap terlihat")
        score += 4

    score = max(0.0, min(100.0, score))
    return ThumbAudit(
        width=w, height=h, aspect=aspect, file_size=len(image_bytes),
        brightness=round(mean, 1), contrast=round(std, 1),
        edge_density=round(extremes, 3), text_ratio=round(extremes, 3),
        score=round(score, 1), issues=issues, notes=notes,
    )


def check_upload_constraints(image_bytes: bytes, fmt: str) -> List[str]:
    """Validasi syarat upload thumbnail resmi: <=2MB, format diterima."""
    errs: List[str] = []
    if len(image_bytes) > MAX_THUMB_SIZE_BYTES:
        errs.append(f"ukuran {len(image_bytes)/1e6:.2f}MB > batas 2MB")
    if fmt and fmt.lower().replace("image/", "") not in {f.split("/")[1] for f in ACCEPTED_FORMATS}:
        errs.append(f"format {fmt} tidak didukung (pakai jpg/png/gif/webp)")
    return errs


def plan_ab_test(thumb_a_path: str, thumb_b_path: str, video_title: str) -> dict:
    """Buat plan A/B test. YouTube 'Test & Compare' (Studio) max 3 variant.

    Output: dict berisi audit kedua variant + hipotesis + cara mengukur.
    """
    plan = {
        "video_title": video_title,
        "variants": [],
        "measurement": [
            "Pakai YouTube Studio 'Test & Compare' (max 3 thumbnail, otomatis dibagi impresi)",
            "Metrik keputusan: watch time share (bukan CTR saja — CTR tinggi + retention rendah = clickbait)",
            "Minimal durasi: hingga >10k impresi per variant ATAU 14 hari, mana yang dulu",
            "Pemenang dipilih YouTube otomatis; catat CTR & AVD sebelum/sesudah",
        ],
        "hypothesis_template": (
            "Variant B mengungguli A pada {metric} karena {reason} "
            "(mis. wajah + teks 3 kata > screenshot polos)"
        ),
    }

    for label, path in (("A", thumb_a_path), ("B", thumb_b_path)):
        with open(path, "rb") as f:
            data = f.read()
        audit = audit_thumbnail(data)
        plan["variants"].append(
            {
                "label": label,
                "path": path,
                "score": audit.score,
                "issues": audit.issues,
                "notes": audit.notes,
            }
        )

    a, b = plan["variants"][0], plan["variants"][1]
    if a["score"] == b["score"]:
        winner = "SERI — pakai Test & Compare untuk memutuskan"
    elif a["score"] > b["score"]:
        winner = f"Variant A unggul skor heuristik ({a['score']} vs {b['score']})"
    else:
        winner = f"Variant B unggul skor heuristik ({b['score']} vs {a['score']})"
    plan["recommendation"] = (
        f"{winner} — tetap biarkan Test & Compare memutuskan dengan data impresi nyata"
    )
    return plan
