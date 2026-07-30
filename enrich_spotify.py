"""Enriches collection.json with Spotify album URLs."""

import base64
import json
import os
import sys
import time

import requests

TOKEN_URL = "https://accounts.spotify.com/api/token"
SEARCH_URL = "https://api.spotify.com/v1/search"


def get_access_token(client_id: str, client_secret: str) -> str:
    resp = requests.post(
        TOKEN_URL,
        data={"grant_type": "client_credentials"},
        headers={
            "Authorization": "Basic "
            + base64.b64encode(f"{client_id}:{client_secret}".encode()).decode(),
        },
        timeout=(5, 10),
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def search_album(session: requests.Session, artist: str, title: str) -> str | None:
    query = f"artist:{artist} album:{title}"
    try:
        resp = session.get(SEARCH_URL, params={"q": query, "type": "album", "limit": 1}, timeout=(5, 10))
    except requests.exceptions.Timeout:
        return None

    if resp.status_code == 429:
        retry_after = int(resp.headers.get("Retry-After", 5))
        if retry_after > 60:
            raise RuntimeError(f"Rate limited for {retry_after}s — try again later")
        print(f"  Rate limited, waiting {retry_after}s...")
        time.sleep(retry_after)
        return search_album(session, artist, title)

    if resp.status_code != 200:
        return None

    items = resp.json().get("albums", {}).get("items", [])
    if not items:
        return None

    return items[0]["external_urls"].get("spotify")


def main():
    client_id = os.environ.get("SPOTIFY_CLIENT_ID")
    client_secret = os.environ.get("SPOTIFY_CLIENT_SECRET")

    if not client_id or not client_secret:
        print("Set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET environment variables")
        sys.exit(1)

    if not os.path.exists("collection.json"):
        print("collection.json not found. Run export_collection.py first:")
        print("  DISCOGS_TOKEN=... uv run python export_collection.py")
        sys.exit(1)

    with open("collection.json") as f:
        collection = json.load(f)

    print(f"Loaded {len(collection)} releases")
    print("Authenticating with Spotify...")
    token = get_access_token(client_id, client_secret)

    session = requests.Session()
    session.headers.update({"Authorization": f"Bearer {token}"})

    found = 0
    for i, release in enumerate(collection):
        if release.get("spotify_url"):
            found += 1
            continue

        artist = release["artists"][0] if release["artists"] else ""
        title = release["title"]

        try:
            url = search_album(session, artist, title)
        except RuntimeError as e:
            print(f"\n{e}")
            print(f"Saving progress ({found} found so far)...")
            break

        release["spotify_url"] = url

        if url:
            found += 1

        print(f"  [{i + 1}/{len(collection)}] {artist} - {title} -> {'found' if url else 'not found'}")

        if (i + 1) % 50 == 0:
            with open("collection.json", "w") as f:
                json.dump(collection, f, indent=2, ensure_ascii=False)

        time.sleep(0.1)

    with open("collection.json", "w") as f:
        json.dump(collection, f, indent=2, ensure_ascii=False)

    print(f"\nDone. {found}/{len(collection)} releases have Spotify URLs.")


if __name__ == "__main__":
    main()
