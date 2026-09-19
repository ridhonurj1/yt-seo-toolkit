"""Tukar authorization code dengan token (langkah 2 dari 2). Non-interaktif.

Pemakaian: python exchange_code.py <client_secret.json> <redirect_url_penuh>
PKCE code_verifier dipulihkan dari ~/.config/ytseo/.code_verifier.
"""

import json
import sys
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from google_auth_oauthlib.flow import InstalledAppFlow

sys.path.insert(0, str(Path(__file__).parent.parent))
from ytseo.client import SCOPES, TOKEN_DIR, TOKEN_PATH  # noqa: E402

PORT = 8765
VERIFIER_PATH = TOKEN_DIR / ".code_verifier"


def main() -> None:
    secrets = sys.argv[1]
    pasted = sys.argv[2].strip()

    q = parse_qs(urlparse(pasted).query)
    if "error" in q:
        raise SystemExit(f"Google mengembalikan error: {q['error']}")
    if "code" not in q:
        raise SystemExit(f"URL tidak memuat ?code=... : {pasted[:200]}")

    flow = InstalledAppFlow.from_client_config(json.loads(Path(secrets).read_text()), SCOPES)
    flow.redirect_uri = f"http://localhost:{PORT}"

    if VERIFIER_PATH.exists():
        flow.code_verifier = VERIFIER_PATH.read_text().strip()
        if not flow.code_verifier:
            raise SystemExit("code_verifier kosong — jalankan ulang print_auth_url.py")
    else:
        raise SystemExit("code_verifier tidak ada — jalankan ulang print_auth_url.py dulu")

    flow.fetch_token(code=q["code"][0])

    TOKEN_DIR.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(flow.credentials.to_json())
    VERIFIER_PATH.unlink(missing_ok=True)
    print(f"OK token tersimpan: {TOKEN_PATH}")


if __name__ == "__main__":
    main()
