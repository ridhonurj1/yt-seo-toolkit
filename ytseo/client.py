"""Klien YouTube Data API v3 + OAuth.

Endpoint yang dipakai:
  * videos.update        — title, description, tags, categoryId, defaultLanguage
  * videos.list          — baca metadata existing untuk audit
  * thumbnails.set       — upload thumbnail custom (butuh verifikasi channel utk >100k video,
                           umumnya langsung aktif)
  * captions.update?     — TIDAK di modul ini (butuh resumable upload terpisah)
  * search.list          — riset keyword kompetitor

OAuth: pakai google-auth-oauthlib InstalledAppFlow. Kredensial client
diharapkan di env YT_CLIENT_SECRETS_JSON (isi JSON mentah) atau path file
YT_CLIENT_SECRETS_FILE. Token cache di ~/.config/ytseo/token.json.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

SCOPES = [
    "https://www.googleapis.com/auth/youtube",           # update metadata + thumbnail
    "https://www.googleapis.com/auth/youtube.force-ssl", # search & list milik sendiri
    "https://www.googleapis.com/auth/youtube.readonly",
]

API_SERVICE_NAME = "youtube"
API_VERSION = "v3"

TOKEN_DIR = Path(os.environ.get("YTSEO_TOKEN_DIR", Path.home() / ".config" / "ytseo"))
TOKEN_PATH = TOKEN_DIR / "token.json"


class YtSeoError(RuntimeError):
    pass


def _client_secrets() -> Dict[str, Any]:
    raw = os.environ.get("YT_CLIENT_SECRETS_JSON")
    if raw:
        return json.loads(raw)
    path = os.environ.get("YT_CLIENT_SECRETS_FILE")
    if path and Path(path).exists():
        return json.loads(Path(path).read_text())
    raise YtSeoError(
        "Kredensial OAuth tidak ditemukan. Set YT_CLIENT_SECRETS_JSON (isi JSON "
        "dari Google Cloud Console > OAuth client > Desktop) atau "
        "YT_CLIENT_SECRETS_FILE=/path/to/client_secret.json"
    )


def get_authenticated_service(port: int = 8765, headless: bool = False):
    """Kembalikan youtube client terautentikasi. Flow OAuth dibuka di browser
    localhost; di server headless pakai run_console / copy-paste URL."""
    creds: Optional[Credentials] = None
    TOKEN_DIR.mkdir(parents=True, exist_ok=True)

    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())

    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_config(_client_secrets(), SCOPES)
        if headless:
            creds = flow.run_console()  # type: ignore[attr-defined]
        else:
            creds = flow.run_local_server(port=port)
        TOKEN_PATH.write_text(creds.to_json())

    return build(API_SERVICE_NAME, API_VERSION, credentials=creds)


def update_metadata(youtube, video_id: str, *, title: Optional[str] = None,
                    description: Optional[str] = None, tags: Optional[List[str]] = None,
                    category_id: str = "22", default_language: Optional[str] = None,
                    made_for_kids: Optional[bool] = None) -> Dict[str, Any]:
    """Update metadata video. Hanya field yang diberikan yang dikirim (API
    videos.update menimpa seluruh snippet — jadi WAJIB ambil existing dulu)."""
    if not (title or description or tags or default_language):
        raise YtSeoError("tidak ada field yang diupdate")

    # AMBIL EXISTING: videos.update menimpa penuh snippet.lalu Kirim balik field lain.
    existing = youtube.videos().list(part="snippet,status", id=video_id).execute()
    items = existing.get("items", [])
    if not items:
        raise YtSeoError(f"video {video_id} tidak ditemukan / bukan milik channel ini")

    snippet = items[0]["snippet"]
    status = items[0].get("status", {})

    if title is not None:
        snippet["title"] = title
    if description is not None:
        snippet["description"] = description
    if tags is not None:
        snippet["tags"] = tags
    if default_language is not None:
        snippet["defaultLanguage"] = default_language

    body: Dict[str, Any] = {"id": video_id, "snippet": snippet}
    if made_for_kids is not None:
        status["madeForKids"] = made_for_kids
        body["status"] = status

    try:
        return youtube.videos().update(part="snippet,status" if made_for_kids is not None else "snippet", body=body).execute()
    except HttpError as e:
        raise YtSeoError(f"update gagal: {e.resp.status} {e.content[:200]}") from e


def set_thumbnail(youtube, video_id: str, image_path: str) -> Dict[str, Any]:
    """Upload thumbnail custom. Butuh Pillow utk validasi dulu (opsional)."""
    path = Path(image_path)
    if not path.exists():
        raise YtSeoError(f"file {image_path} tidak ada")

    from .thumbnail import check_upload_constraints
    data = path.read_bytes()
    fmt = path.suffix.lstrip(".").lower()
    errs = check_upload_constraints(data, f"image/{fmt if fmt != 'jpg' else 'jpeg'}")
    if errs:
        raise YtSeoError("; ".join(errs))

    media = MediaFileUpload(str(path), mimetype=f"image/{'jpeg' if fmt == 'jpg' else fmt}", resumable=False)
    try:
        return youtube.thumbnails().set(videoId=video_id, media_body=media).execute()
    except HttpError as e:
        raise YtSeoError(f"thumbnail set gagal: {e.resp.status} {e.content[:200]}") from e


def get_video(youtube, video_id: str) -> Dict[str, Any]:
    resp = youtube.videos().list(
        part="snippet,statistics,status,contentDetails", id=video_id
    ).execute()
    items = resp.get("items", [])
    if not items:
        raise YtSeoError(f"video {video_id} tidak ditemukan")
    return items[0]


def list_my_videos(youtube, max_results: int = 50) -> List[Dict[str, Any]]:
    """List video milik user yang terautentikasi (uploads playlist)."""
    chans = youtube.channels().list(part="contentDetails,snippet", mine=True).execute()
    items = chans.get("items", [])
    if not items:
        raise YtSeoError("channel tidak ditemukan — cek scope & pilih channel yang benar")
    uploads_playlist = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]

    out: List[Dict[str, Any]] = []
    page_token: Optional[str] = None
    while len(out) < max_results:
        resp = youtube.playlistItems().list(
            part="snippet,contentDetails",
            playlistId=uploads_playlist,
            maxResults=min(50, max_results - len(out)),
            pageToken=page_token,
        ).execute()
        for it in resp.get("items", []):
            vid = it["contentDetails"]["videoId"]
            try:
                out.append(get_video(youtube, vid))
            except YtSeoError:
                continue
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return out


def keyword_research(youtube, query: str, region: str = "ID", lang: str = "id") -> List[Dict[str, Any]]:
    """Riset kompetitor: video teratas untuk query + stat mereka.
    Dipakai untuk melihat pola title/tag yang menang di niche yang sama."""
    resp = youtube.search().list(
        q=query, type="video", part="snippet",
        maxResults=15, regionCode=region, relevanceLanguage=lang,
        order="relevance",
    ).execute()

    ids = [it["id"]["videoId"] for it in resp.get("items", []) if it.get("id", {}).get("videoId")]
    if not ids:
        return []

    stats = youtube.videos().list(part="snippet,statistics", id=",".join(ids)).execute()
    out = []
    for v in stats.get("items", []):
        sn, st = v["snippet"], v.get("statistics", {})
        out.append({
            "video_id": v["id"],
            "title": sn.get("title"),
            "channel": sn.get("channelTitle"),
            "published": sn.get("publishedAt"),
            "views": int(st.get("viewCount", 0)),
            "likes": int(st.get("likeCount", 0)),
            "comments": int(st.get("commentCount", 0)),
            "tags": sn.get("tags", []),
        })
    out.sort(key=lambda x: x["views"], reverse=True)
    return out
