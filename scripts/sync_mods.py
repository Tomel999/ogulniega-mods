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
            return "too_big"
        if dest.exists() and remote_size == dest.stat().st_size:
            return "same"
    except Exception:
        pass

    r = requests.get(url, timeout=60, stream=True)
    r.raise_for_status()
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "wb") as f:
        for chunk in r.iter_content(8192):
            f.write(chunk)
    return "downloaded"


launcher = fetch_json(LAUNCHER_URL)
versions = launcher.get("versions", [])

active_versions = {v["name"] for v in versions}

versions_dir = Path("versions")

if versions_dir.exists():
    for folder in versions_dir.iterdir():
        if folder.is_dir() and folder.name not in active_versions:
            print(f"removing old version: {folder.name}")
            for f in folder.iterdir():
                f.unlink()
            folder.rmdir()

for version in versions:
    name = version["name"]
    print(name)

    try:
        data = fetch_json(VERSION_URL.format(name))
    except Exception as e:
        print(f"  skip: {e}")
        continue

    mods = data.get("mods", [])
    expected_files = {mod["name"] for mod in mods}
    version_dir = versions_dir / name

    if version_dir.exists():
        for existing in version_dir.iterdir():
            if existing.name not in expected_files:
                print(f"  remove {existing.name}")
                existing.unlink()

    for mod in mods:
        dest = version_dir / mod["name"]
        try:
            result = sync_mod(mod["url"], dest)
            if result == "downloaded":
                print(f"  new  {mod['name']}")
            elif result == "same":
                print(f"  ok   {mod['name']}")
            elif result == "too_big":
                pass
        except Exception as e:
            print(f"  err  {mod['name']}: {e}")
