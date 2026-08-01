"""Process 'add-request' GitHub issues: search Discogs, add to collection, close issue."""

import json
import os
import sys
import time

import requests

GITHUB_API = "https://api.github.com"
DISCOGS_API = "https://api.discogs.com"
REPO = "LorenzoCavatorta/music-library-manager"


def get_github_session(token: str) -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    return session


def get_discogs_session(token: str) -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "Authorization": f"Discogs token={token}",
        "User-Agent": "MusicLibraryManager/1.0",
    })
    return session


def fetch_open_requests(gh: requests.Session) -> list[dict]:
    resp = gh.get(
        f"{GITHUB_API}/repos/{REPO}/issues",
        params={"labels": "library-addition-request", "state": "open", "per_page": 50},
    )
    resp.raise_for_status()
    issues = resp.json()
    return [
        i for i in issues
        if not any(l["name"] == "needs-attention" for l in i.get("labels", []))
    ]


def search_discogs(discogs: requests.Session, query: str) -> dict | None:
    resp = discogs.get(
        f"{DISCOGS_API}/database/search",
        params={"q": query, "type": "release", "per_page": 5},
    )
    if resp.status_code == 429:
        print(f"  Rate limited, waiting 60s...")
        time.sleep(60)
        resp = discogs.get(
            f"{DISCOGS_API}/database/search",
            params={"q": query, "type": "release", "per_page": 5},
        )
    resp.raise_for_status()
    results = resp.json().get("results", [])
    if not results:
        return None
    return results[0]


def add_to_discogs_collection(
    discogs: requests.Session, username: str, release_id: int
) -> dict | None:
    resp = discogs.post(
        f"{DISCOGS_API}/users/{username}/collection/folders/1/releases/{release_id}",
    )
    if resp.status_code in (201, 200):
        return resp.json()
    if resp.status_code == 409:
        print(f"  Already in collection (release {release_id})")
        return get_collection_instance(discogs, username, release_id)
    print(f"  Failed to add release {release_id}: {resp.status_code} {resp.text}")
    return None


def get_collection_instance(
    discogs: requests.Session, username: str, release_id: int
) -> dict | None:
    resp = discogs.get(
        f"{DISCOGS_API}/users/{username}/collection/releases/{release_id}",
    )
    if resp.status_code == 200:
        releases = resp.json().get("releases", [])
        if releases:
            return releases[0]
    return None


def fetch_field_ids(discogs: requests.Session, username: str) -> dict[str, int]:
    resp = discogs.get(f"{DISCOGS_API}/users/{username}/collection/fields")
    if resp.status_code != 200:
        return {}
    return {f["name"]: f["id"] for f in resp.json()["fields"]}


def set_custom_fields(
    discogs: requests.Session, username: str, instance: dict,
    field_ids: dict[str, int], custom_fields: dict,
):
    folder_id = instance.get("folder_id", 1)
    release_id = instance["id"] if "id" in instance else instance["basic_information"]["id"]
    instance_id = instance["instance_id"]

    for field_name, value in custom_fields.items():
        if field_name == "Rating":
            continue
        fid = field_ids.get(field_name)
        if not fid:
            print(f"  Warning: unknown field '{field_name}', skipping")
            continue
        resp = discogs.post(
            f"{DISCOGS_API}/users/{username}/collection/folders/{folder_id}/releases/{release_id}/instances/{instance_id}/fields/{fid}",
            json={"value": value},
        )
        if resp.status_code in (200, 204):
            print(f"  Set {field_name} = {value}")
        else:
            print(f"  Failed to set {field_name}: {resp.status_code}")
        time.sleep(0.5)


def set_rating(
    discogs: requests.Session, username: str, instance: dict, rating: int
):
    folder_id = instance.get("folder_id", 1)
    release_id = instance["id"] if "id" in instance else instance["basic_information"]["id"]
    instance_id = instance["instance_id"]
    resp = discogs.post(
        f"{DISCOGS_API}/users/{username}/collection/folders/{folder_id}/releases/{release_id}/instances/{instance_id}",
        json={"rating": rating},
    )
    if resp.status_code in (200, 204):
        print(f"  Set rating = {rating}")
    else:
        print(f"  Failed to set rating: {resp.status_code}")


def close_issue(gh: requests.Session, issue_number: int, comment: str):
    gh.post(
        f"{GITHUB_API}/repos/{REPO}/issues/{issue_number}/comments",
        json={"body": comment},
    )
    gh.patch(
        f"{GITHUB_API}/repos/{REPO}/issues/{issue_number}",
        json={"state": "closed"},
    )


def flag_issue(gh: requests.Session, issue_number: int, comment: str):
    gh.post(
        f"{GITHUB_API}/repos/{REPO}/issues/{issue_number}/comments",
        json={"body": comment},
    )
    gh.post(
        f"{GITHUB_API}/repos/{REPO}/issues/{issue_number}/labels",
        json={"labels": ["needs-attention"]},
    )


def parse_request(issue: dict) -> tuple[str, dict]:
    title = issue["title"]
    for prefix in ("Add:", "add:", "Add ", "add "):
        if title.startswith(prefix):
            title = title[len(prefix):].strip()
            break

    custom_fields = {}
    body = issue.get("body") or ""
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("- **") and ":**" in line:
            key = line.split("**")[1].rstrip(":")
            value = line.split(":** ", 1)[1] if ":** " in line else ""
            if value:
                custom_fields[key] = value

    return title.strip(), custom_fields


def main():
    gh_token = os.environ.get("GH_TOKEN")
    discogs_token = os.environ.get("DISCOGS_TOKEN")

    if not gh_token or not discogs_token:
        print("Set GH_TOKEN and DISCOGS_TOKEN environment variables")
        sys.exit(1)

    gh = get_github_session(gh_token)
    discogs = get_discogs_session(discogs_token)

    identity_resp = discogs.get(f"{DISCOGS_API}/oauth/identity")
    identity_resp.raise_for_status()
    username = identity_resp.json()["username"]
    print(f"Discogs user: {username}")

    issues = fetch_open_requests(gh)
    print(f"Found {len(issues)} open add-request(s)")

    if not issues:
        return

    field_ids = fetch_field_ids(discogs, username)
    print(f"Field IDs: {field_ids}")

    failures = []

    for issue in issues:
        query, custom_fields = parse_request(issue)
        print(f"\nProcessing #{issue['number']}: \"{query}\"")
        if custom_fields:
            print(f"  Fields: {custom_fields}")

        result = search_discogs(discogs, query)
        time.sleep(1)

        if not result:
            flag_issue(
                gh, issue["number"],
                f"Could not find a Discogs release matching: **{query}**\n\n"
                f"Please edit the issue title with a more specific query "
                f"(e.g. include artist and album title) and remove the `needs-attention` label to retry.",
            )
            failures.append(f"#{issue['number']}: no match for \"{query}\"")
            print(f"  No results found, issue left open")
            continue

        release_id = result["id"]
        title = result.get("title", "Unknown")
        year = result.get("year", "?")
        cover = result.get("cover_image", "")

        print(f"  Found: {title} ({year}) [id={release_id}]")

        instance = add_to_discogs_collection(discogs, username, release_id)
        time.sleep(1)

        if instance:
            if custom_fields:
                set_custom_fields(discogs, username, instance, field_ids, custom_fields)
                rating_str = custom_fields.get("Rating")
                if rating_str and rating_str.isdigit():
                    set_rating(discogs, username, instance, int(rating_str))

            comment = (
                f"Added to collection: **{title}** ({year})\n\n"
                f"Discogs release: https://www.discogs.com/release/{release_id}\n"
            )
            if custom_fields:
                comment += "\nCustom fields set:\n"
                for k, v in custom_fields.items():
                    comment += f"- {k}: {v}\n"
            if cover:
                comment += f"\n![cover]({cover})"
            close_issue(gh, issue["number"], comment)
            print(f"  Added and issue closed")
        else:
            flag_issue(
                gh, issue["number"],
                f"Found **{title}** ({year}) but failed to add to collection.\n\n"
                f"Discogs release: https://www.discogs.com/release/{release_id}\n\n"
                f"Remove the `needs-attention` label to retry, or add manually.",
            )
            failures.append(f"#{issue['number']}: failed to add \"{title}\"")
            print(f"  Failed to add, issue left open")

    if failures:
        print(f"\n{'='*50}")
        print(f"FAILED ({len(failures)}):")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)


if __name__ == "__main__":
    main()
