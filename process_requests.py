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
        params={"labels": "add-request", "state": "open", "per_page": 50},
    )
    resp.raise_for_status()
    return resp.json()


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
) -> bool:
    resp = discogs.post(
        f"{DISCOGS_API}/users/{username}/collection/folders/1/releases/{release_id}",
    )
    if resp.status_code in (201, 200):
        return True
    if resp.status_code == 409:
        print(f"  Already in collection (release {release_id})")
        return True
    print(f"  Failed to add release {release_id}: {resp.status_code} {resp.text}")
    return False


def close_issue(gh: requests.Session, issue_number: int, comment: str):
    gh.post(
        f"{GITHUB_API}/repos/{REPO}/issues/{issue_number}/comments",
        json={"body": comment},
    )
    gh.patch(
        f"{GITHUB_API}/repos/{REPO}/issues/{issue_number}",
        json={"state": "closed"},
    )


def parse_request(issue: dict) -> str:
    title = issue["title"]
    for prefix in ("Add:", "add:", "Add ", "add "):
        if title.startswith(prefix):
            return title[len(prefix):].strip()
    return title.strip()


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

    for issue in issues:
        query = parse_request(issue)
        print(f"\nProcessing #{issue['number']}: \"{query}\"")

        result = search_discogs(discogs, query)
        time.sleep(1)

        if not result:
            close_issue(
                gh, issue["number"],
                f"Could not find a Discogs release matching: **{query}**\n\n"
                f"Please try a more specific query (e.g. include artist and album title).",
            )
            print(f"  No results found, issue closed with message")
            continue

        release_id = result["id"]
        title = result.get("title", "Unknown")
        year = result.get("year", "?")
        cover = result.get("cover_image", "")

        print(f"  Found: {title} ({year}) [id={release_id}]")

        added = add_to_discogs_collection(discogs, username, release_id)
        time.sleep(1)

        if added:
            comment = (
                f"Added to collection: **{title}** ({year})\n\n"
                f"Discogs release: https://www.discogs.com/release/{release_id}\n"
            )
            if cover:
                comment += f"\n![cover]({cover})"
            close_issue(gh, issue["number"], comment)
            print(f"  Added and issue closed")
        else:
            close_issue(
                gh, issue["number"],
                f"Found **{title}** ({year}) but failed to add to collection. "
                f"Please try manually: https://www.discogs.com/release/{release_id}",
            )
            print(f"  Failed to add, issue closed with error")


if __name__ == "__main__":
    main()
