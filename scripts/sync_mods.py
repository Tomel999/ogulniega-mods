import os
import requests
from pathlib import Path

LAUNCHER_URL = "https://ogulniega.com/files/launcher.json"
VERSION_URL = "https://ogulniega.com/files/client_versions/{}.json"
MAX_SIZE = 95 * 1024 * 1024

GITHUB_REPO = os.environ["GITHUB_REPOSITORY"]
GH_API = "https://api.github.com"

session = requests.Session()
session.headers.update({
    "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
    "Accept": "application/vnd.github+json",
})


def fetch_json(url):
    r = requests.get(url, timeout=15)
    r.raise_for_status()
    return r.json()


def get_remote_size(url):
    try:
        r = requests.head(url, timeout=10, allow_redirects=True)
        return int(r.headers.get("content-length", -1))
    except Exception:
        return -1


def download_file(url, dest):
    r = requests.get(url, timeout=60, stream=True)
    r.raise_for_status()
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "wb") as f:
        for chunk in r.iter_content(8192):
            f.write(chunk)


def list_releases():
    releases = []
    page = 1
    while True:
        r = session.get(
            f"{GH_API}/repos/{GITHUB_REPO}/releases",
            params={"per_page": 100, "page": page},
            timeout=15,
        )
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        releases.extend(batch)
        page += 1
    return releases


def delete_release(release):
    tag = release["tag_name"]

    r = session.delete(f"{GH_API}/repos/{GITHUB_REPO}/releases/{release['id']}", timeout=15)
    if r.status_code not in (204, 404):
        r.raise_for_status()

    r = session.delete(f"{GH_API}/repos/{GITHUB_REPO}/git/refs/tags/{tag}", timeout=15)
    if r.status_code not in (204, 422, 404):
        r.raise_for_status()

    print(f"  usunięto release: {tag}")


def delete_all_releases():
    print("Usuwanie starych release'ów...")
    releases = list_releases()
    for rel in releases:
        delete_release(rel)
    if not releases:
        print("  brak release'ów do usunięcia")


def create_release(tag, name):
    r = session.post(
        f"{GH_API}/repos/{GITHUB_REPO}/releases",
        json={"tag_name": tag, "name": name, "draft": False, "prerelease": False, "body": f"Mody dla wersji {name}"},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()


def upload_asset(release, filepath):
    upload_url = release["upload_url"].split("{")[0]
    with open(filepath, "rb") as f:
        data = f.read()
    r = session.post(
        upload_url,
        headers={"Content-Type": "application/octet-stream"},
        params={"name": filepath.name},
        data=data,
        timeout=120,
    )
    r.raise_for_status()
    return r.json()["browser_download_url"]


def sync_small_mod(url, dest, remote_size):
    if dest.exists() and remote_size == dest.stat().st_size:
        return "same"
    download_file(url, dest)
    return "downloaded"


def sync_large_mod(url, dest_tmp, release):
    download_file(url, dest_tmp)
    dl_url = upload_asset(release, dest_tmp)
    dest_tmp.unlink(missing_ok=True)
    return dl_url


launcher = fetch_json(LAUNCHER_URL)
versions = launcher.get("versions", [])
active_versions = {v["name"] for v in versions}

versions_dir = Path("versions")
if versions_dir.exists():
    for folder in versions_dir.iterdir():
        if folder.is_dir() and folder.name not in active_versions:
            print(f"Usuwam starą wersję z repo: {folder.name}")
            for f in folder.iterdir():
                f.unlink()
            folder.rmdir()

delete_all_releases()

tmp_dir = Path("/tmp/mod_sync")
tmp_dir.mkdir(parents=True, exist_ok=True)

for version in versions:
    name = version["name"]
    print(f"\n=== {name} ===")

    try:
        data = fetch_json(VERSION_URL.format(name))
    except Exception as e:
        print(f"  skip (błąd pobierania wersji): {e}")
        continue

    mods = data.get("mods", [])
    expected_files = {mod["name"] for mod in mods}

    version_dir = versions_dir / name
    if version_dir.exists():
        for existing in version_dir.iterdir():
            if existing.name not in expected_files:
                print(f"  usuwam stary plik: {existing.name}")
                existing.unlink()

    release = None
    large_mods = []
    small_mods = []

    for mod in mods:
        remote_size = get_remote_size(mod["url"])
        if remote_size > MAX_SIZE:
            large_mods.append((mod, remote_size))
        else:
            small_mods.append((mod, remote_size))

    if large_mods:
        tag = f"mods-{name}"
        print(f"  tworzę release: {tag}")
        release = create_release(tag, name)

    for mod, remote_size in small_mods:
        dest = version_dir / mod["name"]
        try:
            result = sync_small_mod(mod["url"], dest, remote_size)
            print(f"  {'new' if result == 'downloaded' else 'ok '}  {mod['name']}")
        except Exception as e:
            print(f"  err  {mod['name']}: {e}")

    for mod, remote_size in large_mods:
        dest_tmp = tmp_dir / mod["name"]
        try:
            mb = remote_size // 1024 // 1024
            print(f"  big  {mod['name']} ({mb} MB) → release")
            dl_url = sync_large_mod(mod["url"], dest_tmp, release)
            print(f"       asset: {dl_url}")
        except Exception as e:
            print(f"  err  {mod['name']}: {e}")
