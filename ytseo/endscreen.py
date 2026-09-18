"""End screens & cards planner.

Catatan penting (YouTube Data API v3):
  * End screens TIDAK bisa diatur via videos.update. Yang bisa:
    - YouTube Analytics API untuk melihat performa end screen existing
    - YouTube Studio UI untuk mengaturnya (manual)
    - KITA BISA: hitung konfigurasi optimal (durasi, posisi, jenis elemen)
      dan keluarkan checklist/JSON yang tinggal di-setup manual.
  * Cards BISA diatur via API: videos.update?part=cardInfo? TIDAK — cards
    juga tidak ada di videos.update resource resmi. Cards diatur via
    "videoCards" internal Studio / tidak diekspos publik.
  Jadi modul ini = PLANNER + AUDITOR yang menghasilkan resep settingan
  optimal dari durasi & jumlah video/playlist yang tersedia. Output JSON-nya
  dipakai manual di Studio (atau dikirim ke operator).

Struktur end screen resmi (resolusi basis 1280x720, unit relatif 0-1):
  * max 1 video / playlist element + 1 subscribe + 1 channel
  * element ukuran standar: width 0.177, height 0.1 (video), 
    subscribe 0.105 x 0.1
  * minimal tampil 5 detik, maksimal 20 detik (maks 60 utk video <60s tidak bisa)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

END_SCREEN_MAX_DURATION = 20
END_SCREEN_MIN_DURATION = 5
CARD_MAX = 5


@dataclass
class EndScreenElement:
    kind: str  # "video" | "playlist" | "subscribe" | "channel" | "link"
    x: float   # pusat elemen, relatif 0-1
    y: float
    width: float
    height: float
    target: Optional[str] = None  # video_id / playlist_id / url


@dataclass
class EndScreenPlan:
    duration_sec: int
    elements: List[EndScreenElement]
    notes: List[str]


def plan_end_screen(
    video_duration_sec: int,
    has_next_video: bool = True,
    has_subscribe: bool = True,
    has_playlist: bool = False,
    best_video_id: Optional[str] = None,
    playlist_id: Optional[str] = None,
) -> EndScreenPlan:
    """Buat resep end screen optimal sesuai durasi video.

    Aturan praktis dari YouTube Creator Academy:
      * end screen efektif di 8-20 detik terakhir
      * jangan menutupi area konten utama (tengah); letakkan kanan-bawah + kanan-atas
      * subscribe selalu kanan-bawah (dekat tombol player)
    """
    if video_duration_sec < 35:
        return EndScreenPlan(
            duration_sec=0,
            elements=[],
            notes=[
                "video < 35s (Shorts/pindah): end screen tidak tersedia/diabaikan YouTube",
            ],
        )

    duration = min(END_SCREEN_MAX_DURATION, max(END_SCREEN_MIN_DURATION, video_duration_sec // 10))
    elements: List[EndScreenElement] = []
    notes: List[str] = []

    if has_next_video:
        target = best_video_id or ("VIDEO_BARU_LAINNYA")
        elements.append(
            EndScreenElement(
                kind="video", x=0.861, y=0.5, width=0.254, height=0.144,
                target=target,
            )
        )
        notes.append("video besar kanan-tengah: elemen performa CTR tertinggi")

    if (has_playlist or playlist_id) and playlist_id:
        elements.append(
            EndScreenElement(
                kind="playlist", x=0.861, y=0.815, width=0.254, height=0.144,
                target=playlist_id,
            )
        )
        notes.append("playlist kanan-bawah: sesi tonton jadi bertumpuk")

    if has_subscribe:
        elements.append(
            EndScreenElement(
                kind="subscribe", x=0.961, y=0.899, width=0.069, height=0.077,
            )
        )
        notes.append("subscribe pojok kanan-bawah: dekat tombol control player")

    if not elements:
        notes.append("tidak ada elemen yang diminta — end screen kosong tidak berguna")

    return EndScreenPlan(duration_sec=duration, elements=elements, notes=notes)


def plan_cards(
    video_duration_sec: int,
    candidate_points: List[int],
    max_cards: int = CARD_MAX,
) -> List[int]:
    """Sarankan detik kemunculan cards.

    Aturan: jangan dalam 30 detik pertama (viewer belum tertarik), sisirkan
    merata di 2/3 tengah video, maksimal max_cards.
    """
    if video_duration_sec < 60:
        return []

    lo = 30
    hi = max(lo + 1, int(video_duration_sec * 0.9))
    n = min(max_cards, max(1, len(candidate_points)))
    step = (hi - lo) // n
    points = sorted({lo + step * i for i in range(n)})
    return points


def audit_end_screen_json(plan: EndScreenPlan) -> Dict:
    """Serialisasi resep ke JSON-friendly dict (untuk disimpan / dikirim operator)."""
    return {
        "duration_sec": plan.duration_sec,
        "elements": [
            {
                "kind": e.kind,
                "position": {"x": round(e.x, 3), "y": round(e.y, 3)},
                "size": {"w": round(e.width, 3), "h": round(e.height, 3)},
                "target": e.target,
            }
            for e in plan.elements
        ],
        "notes": plan.notes,
        "studio_steps": [
            "Buka YouTube Studio > konten > video target",
            "Tab 'End screens' di timeline bawah editor",
            f"Set durasi elemen = {plan.duration_sec}s dari akhir video",
            *[f"Tambahkan elemen {e.kind}" + (f" target {e.target}" if e.target else "") for e in plan.elements],
        ],
    }
