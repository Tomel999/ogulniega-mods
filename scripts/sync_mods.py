import requests
from pathlib import Path

LAUNCHER_URL = "https://ogulniega.com/files/launcher.json"
VERSION_URL = "https://ogulniega.com/files/client_versions/{}.json"
MAX_SIZE = 95 * 1024 * 1024


def fetch_json(url):
    r = requests.get(url, timeout=15)
    r.raise_for_status()
    return r.json()


def sync_mod(url, dest):
    try:
        head = requests.head(url, timeout=10, allow_redirects=True)
        remote_size = int(head.headers.get("content-length", -1))
        if remote_size > MAX_SIZE:
            print(f"  skip (za duży: {remote_size // 1024 // 1024} MB)")
            return False
        if dest.exists() and remote_size == dest.stat().st_size:
            return False
    except Exception:
        pass

    r = requests.get(url, timeout=60, stream=True)
    r.raise_for_status()
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "wb") as f:
        for chunk in r.iter_content(8192):
            f.write(chunk)
    return True


launcher = fetch_json(LAUNCHER_URL)
versions = launcher.get("versions", [])

for version in versions:
    name = version["name"]
    print(name)

    try:
        data = fetch_json(VERSION_URL.format(name))
    except Exception as e:
        print(f"  skip: {e}")
        continue

    for mod in data.get("mods", []):
        dest = Path("versions") / name / mod["name"]
        try:
            changed = sync_mod(mod["url"], dest)
            if changed is not False:
                print(f"  {'new' if changed else 'ok '} {mod['name']}")
        except Exception as e:
            print(f"  err {mod['name']}: {e}")
