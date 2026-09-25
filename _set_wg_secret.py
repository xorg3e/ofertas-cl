import base64
import json
import subprocess
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import nacl.secret  # noqa: E402

REPO = "xorg3e/ofertas-cl"
SECRET_NAME = "WG_CONF"
CONF_PATH = r"C:\Users\franc\OneDrive - Universidad Mayor\Escritorio\campo.conf"


def git_cred() -> tuple[str, str]:
    out = subprocess.run(
        ["git", "credential", "fill"],
        input="protocol=https\nhost=github.com\n\n",
        capture_output=True,
        text=True,
    )
    user = pw = ""
    for line in out.stdout.splitlines():
        if line.startswith("username="):
            user = line[9:]
        elif line.startswith("password="):
            pw = line[8:]
    return user, pw


def api(method: str, path: str, token: str, body: dict | None = None):
    req = urllib.request.Request(
        f"https://api.github.com{path}",
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "Authorization": f"Basic {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req) as r:
            raw = r.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        print("HTTP", e.code, e.read().decode()[:300])
        raise


user, pw = git_cred()
basic = base64.b64encode(f"{user}:{pw}".encode()).decode()
repo = REPO

pub = api("GET", f"/repos/{repo}/actions/secrets/public-key", basic)
key = base64.b64decode(pub["key"])
with open(CONF_PATH, "rb") as f:
    conf = f.read()
box = nacl.secret.SecretBox(key)
sealed = base64.b64encode(box.encrypt(conf)).decode()

api(
    "PUT",
    f"/repos/{repo}/actions/secrets/{SECRET_NAME}",
    basic,
    {"encrypted_value": sealed, "key_id": pub["key_id"]},
)

secrets = api("GET", f"/repos/{repo}/actions/secrets", basic)
print("secrets:", [s["name"] for s in secrets["secrets"]])
