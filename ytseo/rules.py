"""Aturan SEO metadata: title, description, tags — murni fungsi, tanpa I/O.

Semua fungsi deterministik supaya gampang dites. Batas mengikuti resmi
YouTube Creator Academy:
  * title       -> 100 char (hard cut di API, pakai 70 sebagai zona aman mobile)
  * description -> 5000 char; 150 char pertama tampil di snippet search
  * tags        -> 500 char total gabungan
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Tuple

TITLE_SAFE_LIMIT = 70
TITLE_HARD_LIMIT = 100
DESCRIPTION_LIMIT = 5000
DESCRIPTION_SNIPPET_CHARS = 150
TAGS_TOTAL_LIMIT = 500
MAX_TAGS = 30

# Stopword kata sambung yang tidak jadi tag (ID + EN ringkas)
_STOPWORDS = {
    "dan", "atau", "yang", "di", "ke", "dari", "untuk", "pada", "dengan",
    "the", "a", "an", "of", "to", "in", "on", "for", "with", "and", "or",
    "is", "are", "how", "what", "cara", "tutorial", "video",
}


@dataclass
class TitleAudit:
    original: str
    issues: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues


def audit_title(title: str) -> TitleAudit:
    """Audit title: panjang, clickbait kosong, kata kunci di depan."""
    t = (title or "").strip()
    audit = TitleAudit(original=t)

    if not t:
        audit.issues.append("title kosong")
        return audit

    if len(t) > TITLE_HARD_LIMIT:
        audit.issues.append(f"title {len(t)} char > batas API {TITLE_HARD_LIMIT}")
    elif len(t) > TITLE_SAFE_LIMIT:
        audit.issues.append(
            f"title {len(t)} char > zona aman mobile {TITLE_SAFE_LIMIT} "
            "(ekor terpotong di tampilan mobile/search)"
        )
        audit.suggestions.append(t[:TITLE_SAFE_LIMIT].rstrip() + "…")

    # Angka spesifik & keyword depan = CTR bagus; VAGUE CAPS = buruk
    if not re.search(r"\d", t):
        audit.suggestions.append("pertimbangkan angka spesifik (mis. '3 Cara…' performa CTR lebih baik)")

    if t.upper() == t and len(t) > 20 and any(c.isalpha() for c in t):
        audit.issues.append("title ALL-CAPS — dianggap spam oleh algoritma & viewer")
        audit.suggestions.append(t.capitalize())

    if re.search(r"(!!+|\?\?+|\*\*\+)", t):
        audit.issues.append("tanda seru/tanya berlebihan menurunkan trust")

    return audit


def build_description(
    hook: str,
    body_lines: List[str],
    links: List[str] | None = None,
    hashtags: List[str] | None = None,
    chapters: str | None = None,
) -> str:
    """Susun description terstruktur. 150 char pertama = hook + keyword utama
    (snippet search). Chapters ditaruh SETELAH hook agar tetap terbaca di
    desktop tetapi tidak menggeser snippet."""
    parts: List[str] = []
    hook = (hook or "").strip()
    if hook:
        parts.append(hook)

    if chapters:
        parts.append(chapters.strip())

    parts.append("")
    parts.extend(l.rstrip() for l in body_lines)

    links = [l.strip() for l in (links or []) if l.strip()]
    if links:
        parts.append("")
        parts.append("🔗 LINK:")
        parts.extend(links)

    tags = [h if h.startswith("#") else f"#{h}" for h in (hashtags or [])][:15]
    if tags:
        parts.append("")
        parts.append(" ".join(tags))

    desc = "\n".join(parts)
    if len(desc) > DESCRIPTION_LIMIT:
        desc = desc[: DESCRIPTION_LIMIT - 1].rstrip() + "…"
    return desc


def description_snippet(desc: str) -> str:
    """150 char pertama yang tampil di snippet search — harus memuat hook."""
    d = (desc or "").strip().replace("\n", " ")
    return d[:DESCRIPTION_SNIPPET_CHARS]


def extract_hashtags_from_text(text: str) -> List[str]:
    """Ambil #hashtag dari teks (untuk audit hashtags di description)."""
    found = re.findall(r"#([\w\u00C0-\u024F]+)", text or "")
    seen: List[str] = []
    for h in found:
        if h.lower() not in {s.lower() for s in seen}:
            seen.append(h)
    return seen[:15]  # YouTube: >15 hashtag = semua diabaikan


def normalize_tags(raw: List[str]) -> List[str]:
    """Bersihkan & dedupe tag, jaga total <=500 char dan <=30 tag.
    Urutan penting: tag pertama = keyword paling penting."""
    out: List[str] = []
    total = 0
    for t in raw or []:
        t = re.sub(r"[\"<>]", "", (t or "")).strip()
        if not t:
            continue
        t = t.lower()
        if t in out:
            continue
        cost = len(t) + (1 if out else 0)  # koma pemisah dihitung YouTube
        if len(out) >= MAX_TAGS or total + cost > TAGS_TOTAL_LIMIT:
            break
        out.append(t)
        total += cost
    return out


def suggest_tags_from_title_and_desc(title: str, description: str, extra: List[str] | None = None) -> List[str]:
    """Heuristic sederhana: unigram/bigram dari title + extra + hashtag desc.
    Tags diurutkan: extra (explicit) -> bigram title -> unigram konten."""
    words = [
        w.lower()
        for w in re.findall(r"[\w\u00C0-\u024F]+", f"{title} {description or ''}")
        if w.lower() not in _STOPWORDS and len(w) > 2
    ]

    title_words = [
        w.lower()
        for w in re.findall(r"[\w\u00C0-\u024F]+", title or "")
        if w.lower() not in _STOPWORDS and len(w) > 2
    ]

    bigrams = [
        f"{title_words[i]} {title_words[i+1]}"
        for i in range(len(title_words) - 1)
    ]

    candidates: List[str] = list(dict.fromkeys((extra or []) + bigrams + title_words))
    return normalize_tags(candidates)


def tags_total_length(tags: List[str]) -> int:
    """Total char yang dihitung YouTube: gabungan dipisah koma."""
    if not tags:
        return 0
    return sum(len(t) for t in tags) + len(tags) - 1


def audit_tags(tags: List[str]) -> Tuple[List[str], List[str]]:
    """Kembalikan (issues, cleaned). Tag >30 item / >500 char dipangkas API."""
    cleaned = normalize_tags(tags)
    issues: List[str] = []
    if len(tags or []) > MAX_TAGS:
        issues.append(f"{len(tags)} tag > batas {MAX_TAGS}, dipangkas")
    if tags_total_length(tags or []) > TAGS_TOTAL_LIMIT:
        issues.append(f"total {tags_total_length(tags)} char > batas {TAGS_TOTAL_LIMIT}, dipangkas")
    if len(cleaned) < 5:
        issues.append(f"tag cuma {len(cleaned)} — target 10-20 relevan")
    return issues, cleaned
