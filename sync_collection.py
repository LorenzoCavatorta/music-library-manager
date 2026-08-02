"""Sync collection from Discogs, preserving repo-only fields (e.g. spotify_url)."""

import json
import os
import sys

from export_collection import fetch_collection, fetch_identity, get_session, resolve_field_names

REPO_ONLY_FIELDS = {"spotify_url"}


def main():
    token = os.environ.get("DISCOGS_TOKEN")
    if not token:
        print("Set the DISCOGS_TOKEN environment variable")
        sys.exit(1)

    session = get_session(token)
    username = fetch_identity(session)
    print(f"Authenticated as: {username}")

    existing = {}
    if os.path.exists("collection.json"):
        with open("collection.json") as f:
            for release in json.load(f):
                existing[release["id"]] = release

    print(f"Existing collection: {len(existing)} releases")

    releases = fetch_collection(session, username)
    releases = resolve_field_names(session, username, releases)

    for release in releases:
        old = existing.get(release["id"])
        if old:
            for field in REPO_ONLY_FIELDS:
                if field in old:
                    release[field] = old[field]

    with open("collection.json", "w") as f:
        json.dump(releases, f, indent=2, ensure_ascii=False)

    added = len(releases) - len(existing)
    removed = len(existing) - len(releases)
    print(f"\nSynced: {len(releases)} releases (added {max(0, added)}, removed {max(0, removed)})")


if __name__ == "__main__":
    main()
