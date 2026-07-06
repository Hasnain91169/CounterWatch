"""
Download local hero portrait icons for the browser app.

The source endpoint returns portrait URLs for Overwatch heroes. Images are
stored under web/assets/heroes/{local_slug}.png so the app works offline after
the download has completed.
"""

import json
import sys
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "web" / "assets" / "heroes"
MANIFEST = OUT / "manifest.json"
SOURCE = "https://overfast-api.tekrop.fr/heroes"

KEY_OVERRIDES = {
    "junker_queen": "junker-queen",
    "jetpack_cat": "jetpack-cat",
    "soldier76": "soldier-76",
    "wrecking_ball": "wrecking-ball",
}


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def fetch_json(url):
    with urllib.request.urlopen(url, timeout=30) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return json.loads(response.read().decode(charset))


def fetch_bytes(url):
    request = urllib.request.Request(url, headers={"User-Agent": "ow-counterpick-local/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def overfast_key(slug):
    return KEY_OVERRIDES.get(slug, slug.replace("_", "-"))


def main():
    heroes = {
        slug: hero
        for slug, hero in read_json(DATA / "heroes.json").items()
        if not slug.startswith("_")
    }
    source_rows = fetch_json(SOURCE)
    by_key = {row["key"]: row for row in source_rows}

    OUT.mkdir(parents=True, exist_ok=True)
    manifest = {"source": SOURCE, "heroes": {}, "missing": []}

    for slug in sorted(heroes):
        key = overfast_key(slug)
        row = by_key.get(key)
        if not row or not row.get("portrait"):
            manifest["missing"].append(slug)
            print(f"missing: {slug} ({key})")
            continue

        target = OUT / f"{slug}.png"
        data = fetch_bytes(row["portrait"])
        target.write_bytes(data)
        manifest["heroes"][slug] = {
            "source_key": key,
            "source_name": row.get("name"),
            "source_url": row["portrait"],
            "file": f"{slug}.png",
            "bytes": len(data),
        }
        print(f"downloaded: {slug} -> {target.name} ({len(data)} bytes)")

    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if manifest["missing"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
