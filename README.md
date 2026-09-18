# yt-seo-toolkit

Tool SEO YouTube 100% sah via **YouTube Data API v3** — optimasi metadata, thumbnail, chapters, end screens, riset keyword. Tanpa fake views, tanpa proxy. Yang dioptimasi adalah **metadata & strategi**, bukan menipu metrik.

## Fitur

| Modul | Fungsi |
|---|---|
| `ytseo.rules` | Audit & generator title (batas 100/70 char, anti-ALL-CAPS), description builder (150-char snippet hook), tags normalizer (batas 500 char / 30 tag), auto-suggest tags |
| `ytseo.chapters` | Parser & validator chapters (syarat resmi: ≥3 timestamp, mulai 00:00, tiap chapter ≥10s) |
| `ytseo.endscreen` | Planner end screen (posisi & durasi optimal per durasi video) + cards schedule; output JSON + checklist Studio |
| `ytseo.thumbnail` | Auditor thumbnail (rasio, brightness, kontras, area teks) + planner A/B test via YouTube "Test & Compare" |
| `ytseo.client` | OAuth + videos.update (read-modify-write yang aman), thumbnails.set, list video sendiri, keyword research kompetitor |

## Setup

```bash
pip install -r requirements.txt

# 1. Google Cloud Console > buat project > enable "YouTube Data API v3"
# 2. Credentials > Create OAuth client ID > Desktop app > download JSON
export YT_CLIENT_SECRETS_FILE=/path/to/client_secret_xxx.json

# API key untuk perintah read-only (audit video publik, tanpa OAuth):
export YT_API_KEY=AIza...
```

## Pemakaian

```bash
# Audit video publik (pakai API key):
python -m ytseo.cli audit "https://youtube.com/watch?v=XXXX"

# Autentikasi sekali (browser terbuka):
python -m ytseo.cli auth

# List video channel sendiri:
python -m ytseo.cli list

# Update metadata (read-modify-write: field lain tidak hilang):
python -m ytseo.cli optimize VIDEO_ID \
  --title "3 Cara ... (2026)" \
  --desc-file desc.txt \
  --suggest-tags

# Upload thumbnail:
python -m ytseo.cli thumb-set VIDEO_ID thumbnail.jpg

# Riset title & tag kompetitor:
python -m ytseo.cli research "cara menanam cabai hidroponik"

# Validasi chapters sebelum dipakai:
python -m ytseo.cli chapters chapters.txt

# Audit + A/B thumbnail:
python -m ytseo.cli thumb thumbnail.jpg
python -m ytseo.cli abtest a.jpg b.jpg "Judul Video"
```

## End screens & cards — keterbatasan API yang jujur

YouTube **tidak mengekspos** end screens & cards lewat Data API v3 (hanya via Studio). Tool ini menghasilkan **resep settingan optimal** (posisi, durasi, jenis elemen, jadwal cards) dalam JSON + langkah-langkah Studio — setup manual 30 detik per video.

## Peta jalan

- [x] Audit metadata offline rules
- [x] Chapters validator
- [x] Thumbnail auditor + A/B planner
- [x] OAuth client + metadata update + thumbnail upload
- [ ] Hasil A/B test via YouTube Analytics API (per-variant CTR & watch time)
- [ ] Dashboard web (FastAPI + polling) — antrian optimasi massal
- [ ] Auto-chapters dari transkrip (whisper)

## Etika

Tool ini tidak dan tidak akan: memutar video otomatis, mensimulasikan penonton, memakai proxy untuk menggandakan impresi. Semua yang dilakukan adalah optimasi metadata yang tersedia via API resmi untuk pemilik channel sendiri. Fake engagement melanggar YouTube ToS dan merusak ekosistem iklan.
