"""Enriches collection.json with Spotify album URLs for entries that don't have one."""

import base64
import json
import os
import re
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
    queries = [
        f"artist:{artist} album:{title}",
        f"{artist} {title}",
    ]
    for query in queries:
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
            try:
                resp = session.get(SEARCH_URL, params={"q": query, "type": "album", "limit": 1}, timeout=(5, 10))
            except requests.exceptions.Timeout:
                return None

        if resp.status_code != 200:
            return None

        items = resp.json().get("albums", {}).get("items", [])
        if items:
            return items[0]["external_urls"].get("spotify")

    return None


def main():
    client_id = os.environ.get("SPOTIFY_CLIENT_ID")
    client_secret = os.environ.get("SPOTIFY_CLIENT_SECRET")

    if not client_id or not client_secret:
        print("Set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET environment variables")
        sys.exit(1)

    if not os.path.exists("collection.json"):
        print("collection.json not found")
        sys.exit(1)

    with open("collection.json") as f:
        collection = json.load(f)

    to_enrich = [r for r in collection if "spotify_url" not in r]
    print(f"Loaded {len(collection)} releases ({len(to_enrich)} need Spotify lookup)")

    if not to_enrich:
        print("Nothing to do.")
        return

    print("Authenticating with Spotify...")
    token = get_access_token(client_id, client_secret)

    session = requests.Session()
    session.headers.update({"Authorization": f"Bearer {token}"})

    found = 0
    rate_limited = False
    for i, release in enumerate(to_enrich):
        artist = re.sub(r"\s*\(\d+\)$", "", release["artists"][0]) if release["artists"] else ""
        title = release["title"]

        try:
            url = search_album(session, artist, title)
        except RuntimeError as e:
            print(f"\n{e}")
            print(f"Saving progress...")
            rate_limited = True
            break

        release["spotify_url"] = url

        if url:
            found += 1

        print(f"  [{i + 1}/{len(to_enrich)}] {artist} - {title} -> {'found' if url else 'not found'}")

        if (i + 1) % 50 == 0:
            with open("collection.json", "w") as f:
                json.dump(collection, f, indent=2, ensure_ascii=False)

        time.sleep(0.1)

    with open("collection.json", "w") as f:
        json.dump(collection, f, indent=2, ensure_ascii=False)

    remaining = len(to_enrich) - found - (len(to_enrich) - i - 1 if not rate_limited else 0)
    print(f"\nDone. Enriched {found} of {len(to_enrich)} new releases with Spotify URLs.")

    if rate_limited:
        print(f"::warning::Spotify rate limit hit. {len(to_enrich) - i - 1} releases still need enrichment. Re-run later.")
        sys.exit(2)


if __name__ == "__main__":
    main()
