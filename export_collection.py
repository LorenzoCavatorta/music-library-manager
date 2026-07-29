import json
import os
import sys
import time

import requests

BASE_URL = "https://api.discogs.com"


def get_session(token: str) -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "Authorization": f"Discogs token={token}",
        "User-Agent": "MusicLibraryManager/1.0",
    })
    return session


def fetch_identity(session: requests.Session) -> str:
    resp = session.get(f"{BASE_URL}/oauth/identity")
    resp.raise_for_status()
    return resp.json()["username"]


def fetch_collection(session: requests.Session, username: str) -> list[dict]:
    # get total count
    resp = session.get(f"{BASE_URL}/users/{username}/collection/folders/0")
    resp.raise_for_status()
    print(f"Found {resp.json()['count']} releases in collection")

    releases = []
    page = 1
    per_page = 100

    while True:
        resp = session.get(
            f"{BASE_URL}/users/{username}/collection/folders/0/releases",
            params={"page": page, "per_page": per_page},
        )

        if resp.status_code == 429:
            print("Rate limited, waiting 60s...")
            time.sleep(60)
            continue

        resp.raise_for_status()
        data = resp.json()

        for item in data["releases"]:
            release_info = item["basic_information"]
            record = {
                "id": release_info["id"],
                "title": release_info["title"],
                "artists": [a["name"] for a in release_info["artists"]],
                "year": release_info["year"],
                "labels": [l["name"] for l in release_info["labels"]],
                "formats": [f["name"] for f in release_info["formats"]],
                "genres": release_info.get("genres", []),
                "styles": release_info.get("styles", []),
                "rating": item.get("rating", 0),
                "date_added": item.get("date_added"),
                "custom_fields": {},
            }

            if "notes" in item:
                for note in item["notes"]:
                    record["custom_fields"][note["field_id"]] = note["value"]

            releases.append(record)

        pagination = data["pagination"]
        print(f"  Page {page}/{pagination['pages']} ({len(releases)} releases so far)")

        if page >= pagination["pages"]:
            break
        page += 1
        time.sleep(1)

    return releases


def resolve_field_names(session: requests.Session, username: str, releases: list[dict]) -> list[dict]:
    resp = session.get(f"{BASE_URL}/users/{username}/collection/fields")

    if resp.status_code != 200:
        print("Warning: couldn't fetch custom field names, using field IDs")
        return releases

    fields = {f["id"]: f["name"] for f in resp.json()["fields"]}
    print(f"Custom fields: {fields}")

    for release in releases:
        named_fields = {}
        for field_id, value in release["custom_fields"].items():
            field_name = fields.get(field_id, f"field_{field_id}")
            named_fields[field_name] = value
        release["custom_fields"] = named_fields

    return releases


def main():
    token = os.environ.get("DISCOGS_TOKEN")
    if not token:
        print("Set the DISCOGS_TOKEN environment variable with your personal access token")
        sys.exit(1)

    session = get_session(token)
    username = fetch_identity(session)
    print(f"Authenticated as: {username}")

    releases = fetch_collection(session, username)
    releases = resolve_field_names(session, username, releases)

    output_path = "collection.json"
    with open(output_path, "w") as f:
        json.dump(releases, f, indent=2, ensure_ascii=False)

    print(f"\nExported {len(releases)} releases to {output_path}")


if __name__ == "__main__":
    main()
