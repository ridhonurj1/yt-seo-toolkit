"""OAuth manual-paste flow untuk server headless.

Mekanisme (OOB deprecated, jadi pakai redirect ke localhost yang TIDAK
perlu server aktif di mesin ini):
  1. Tool cetak URL authorization (scope youtube + force-ssl + readonly)
  2. User buka URL DI PERANGKAT MANA PUN (HP), login, izinkan
  3. Google redirect ke http://localhost:PORT/?code=... — di HP halaman itu
     error (wajar). User copy URL FULL dari address bar HP, paste balik sini.
  4. Tool tukar code dengan token, simpan ke ~/.config/ytseo/token.json

Redirect URI yang dipakai: http://localhost:1 (port 1 hampir pasti tak
dipakai apa pun; Google Desktop client mengizinkan http://localhost
dengan port bebas). Kalau http://localhost:1 ditolak consent, fallback
http://localhost:8765.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

from .client import SCOPES, TOKEN_DIR, TOKEN_PATH


def run_manual_flow(client_secrets_path: str, redirect_port: int = 8765) -> Path:
    flow = InstalledAppFlow.from_client_config(
        json.loads(Path(client_secrets_path).read_text()), SCOPES
    )
    # redirect_uri harus terdaftar di client Google; Desktop app otomatis
    # punya http://localhost (port bebas) — kita pakai port eksplisit.
    flow.redirect_uri = f"http://localhost:{redirect_port}"

    auth_url, _ = flow.authorization_url(
        access_type="offline", include_granted_scopes="true", prompt="consent"
    )

    print("=" * 70)
    print("LANGKAH 1 — buka URL ini di HP/browser mana pun:")
    print()
    print(auth_url)
    print()
    print("LANGKAH 2 — login & tekan 'Allow' (lanjutkan meski muncul")
    print("            warning 'unverified app' → Advanced → Go to app)")
    print("LANGKAH 3 — browser akan redirect ke http://localhost:%d/?code=..." % redirect_port)
    print("            Halaman itu PASTI error (tidak ada server). TIDAK APA-APA.")
    print("            Copy URL LENGKAP dari address bar, paste di bawah.")
    print("=" * 70)

    pasted = input("URL redirect penuh: ").strip()
    # Ambil query code dari URL yang dipaste
    from urllib.parse import urlparse, parse_qs
    q = parse_qs(urlparse(pasted).query)
    if "code" not in q:
        raise SystemExit(f"URL tidak memuat ?code=... : {pasted[:120]}")
    flow.fetch_token(code=q["code"][0])

    TOKEN_DIR.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(flow.credentials.to_json())
    print(f"\n✅ token tersimpan: {TOKEN_PATH}")
    return TOKEN_PATH


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else os.environ.get(
        "YT_CLIENT_SECRETS_FILE", "client_secret.json"
    )
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 8765
    run_manual_flow(path, port)
