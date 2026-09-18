"""Chapters builder & validator.

Syarat resmi YouTube chapters:
  * minimal 3 timestamp
  * timestamp pertama harus 00:00
  * tiap chapter minimal 10 detik
  * format: "00:00 Judul" (timestamp lalu spasi lalu judul)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Tuple

TS_PATTERN = re.compile(r"^\s*(\d{1,2}:\d{2}(:\d{2})?)\s+(.+?)\s*$")
MIN_CHAPTER_SECONDS = 10
MIN_CHAPTERS = 3


@dataclass
class Chapter:
    seconds: int
    stamp: str
    title: str


def _stamp_to_seconds(stamp: str) -> int:
    parts = [int(p) for p in stamp.split(":")]
    if len(parts) == 2:
        m, s = parts
        return m * 60 + s
    h, m, s = parts
    return h * 3600 + m * 60 + s


def _seconds_to_stamp(total: int) -> str:
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def parse_chapters(text: str) -> Tuple[List[Chapter], List[str]]:
    """Parse teks chapters multi-baris. Kembalikan (chapters, errors)."""
    chapters: List[Chapter] = []
    errors: List[str] = []

    for idx, line in enumerate((text or "").strip().splitlines()):
        if not line.strip():
            continue
        m = TS_PATTERN.match(line)
        if not m:
            errors.append(f"baris {idx + 1}: format tidak dikenali (butuh 'MM:SS Judul'): {line.strip()!r}")
            continue
        stamp, title = m.group(1), m.group(3)
        chapters.append(Chapter(_stamp_to_seconds(stamp), stamp, title))

    if not chapters:
        errors.append("tidak ada chapter terdeteksi")
        return chapters, errors

    if chapters[0].seconds != 0:
        errors.append("chapter pertama wajib 00:00 (syarat YouTube)")
    if len(chapters) < MIN_CHAPTERS:
        errors.append(f"chapter {len(chapters)} < minimal {MIN_CHAPTERS}")

    for i in range(1, len(chapters)):
        if chapters[i].seconds <= chapters[i - 1].seconds:
            errors.append(
                f"chapter #{i + 1} ({chapters[i].stamp}) tidak boleh <= sebelumnya ({chapters[i - 1].stamp})"
            )
        elif chapters[i].seconds - chapters[i - 1].seconds < MIN_CHAPTER_SECONDS:
            errors.append(
                f"chapter #{i} terlalu pendek ({chapters[i].seconds - chapters[i - 1].seconds}s < {MIN_CHAPTER_SECONDS}s)"
            )

    return chapters, errors


def build_chapters_block(items: List[Tuple[int, str]]) -> str:
    """Buat blok chapters dari list [(detik, judul)]. Stamp pertama dinormalisasi ke 00:00.
    Raises ValueError bila tidak memenuhi syarat YouTube — fail-loud, bukan diam-diam
    membuat chapters yang tidak aktif."""
    if len(items) < MIN_CHAPTERS:
        raise ValueError(f"butuh >= {MIN_CHAPTERS} chapter, dapat {len(items)}")

    lines: List[str] = []
    prev = -1
    for sec, title in items:
        sec = max(0, int(sec))
        if prev >= 0 and sec - prev < MIN_CHAPTER_SECONDS:
            raise ValueError(
                f"chapter '{title}' hanya {sec - prev}s dari sebelumnya (minimal {MIN_CHAPTER_SECONDS}s)"
            )
        prev = sec
        lines.append(f"{_seconds_to_stamp(sec)} {title.strip()}")

    block = "\n".join(lines)
    # Force stamp pertama 00:00
    first = items[0][0]
    if first != 0:
        raise ValueError(f"chapter pertama harus detik 0, dapat {first}")
    return block


def validate_block(block: str) -> List[str]:
    """Validasi blok jadi — list kosong berarti lolos semua syarat."""
    _, errors = parse_chapters(block)
    return errors
