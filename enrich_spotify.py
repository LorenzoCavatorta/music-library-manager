"""Adds Spotify album URLs to collection.json entries that don't have one.

Records with no link (missing or null) are (re)tried on every run. A record only
gets a link when spotify.find_album finds a confident artist + title match; API
errors leave the record untouched so it is retried next time, instead of being
recorded as "not found".
"""

import json
import os
import sys
import time

from spotify import Spotify, SpotifyError

SAVE_EVERY = 50


def main():
    sp = Spotify.from_env()
    if sp is None:
        print("Set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET environment variables")
        sys.exit(1)

    if not os.path.exists("collection.json"):
        print("collection.json not found")
        sys.exit(1)

    with open("collection.json") as f:
        collection = json.load(f)

    to_enrich = [r for r in collection if not r.get("spotify_url")]
    print(f"Loaded {len(collection)} releases ({len(to_enrich)} without a Spotify link)")

    found = errors = 0
    stopped_early = False
    for i, release in enumerate(to_enrich):
        label = f"{', '.join(release['artists'])} - {release['title']}"
        try:
            match = sp.find_album(release["artists"], release["title"], release.get("year") or None)
        except SpotifyError as e:
            errors += 1
            print(f"  [{i + 1}/{len(to_enrich)}] {label} -> error: {e}")
            if "rate limited" in str(e):
                stopped_early = True
                break
            continue

        release["spotify_url"] = match["url"] if match else None
        if match:
            found += 1
            print(f"  [{i + 1}/{len(to_enrich)}] {label} -> {', '.join(match['artists'])} - {match['name']}")
        else:
            print(f"  [{i + 1}/{len(to_enrich)}] {label} -> no confident match")

        if (i + 1) % SAVE_EVERY == 0:
            with open("collection.json", "w") as f:
                json.dump(collection, f, indent=2, ensure_ascii=False)
        time.sleep(0.1)

    with open("collection.json", "w") as f:
        json.dump(collection, f, indent=2, ensure_ascii=False)

    print(f"\nDone. Found links for {found} of {len(to_enrich)} releases ({errors} errors).")
    if stopped_early or errors:
        print("::warning::Spotify enrichment was incomplete (rate limit or API errors). Re-run later to finish.")
        sys.exit(2)


if __name__ == "__main__":
    main()
