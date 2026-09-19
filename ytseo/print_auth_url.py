"""Cetak URL authorization OAuth (langkah 1 dari 2). Non-interaktif.

PKCE: code_verifier WAJIB sama antara langkah 1 dan 2 — simpan ke disk
supaya exchange_code.py bisa memulihkannya (default: hilang saat exit).
"""

import json
import sys
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

sys.path.insert(0, str(Path(__file__).parent.parent))
from ytseo.client import SCOPES, TOKEN_DIR  # noqa: E402

PORT = 8765
VERIFIER_PATH = TOKEN_DIR / ".code_verifier"

flow = InstalledAppFlow.from_client_config(
    json.loads(Path(sys.argv[1] if len(sys.argv) > 1 else "client_secret.json").read_text()),
    SCOPES,
)
flow.redirect_uri = f"http://localhost:{PORT}"
url, _ = flow.authorization_url(access_type="offline", include_granted_scopes="true", prompt="consent")

TOKEN_DIR.mkdir(parents=True, exist_ok=True)
VERIFIER_PATH.write_text(flow.code_verifier or "")
VERIFIER_PATH.chmod(0o600)
print(url, flush=True)
print(f"# verifier disimpan: {VERIFIER_PATH}", file=sys.stderr)
