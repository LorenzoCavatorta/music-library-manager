"""Process 'add-request' GitHub issues: search Discogs, add to collection, update collection.json."""

import json
import os
import re
import sys
import time

import requests

from spotify import Spotify, SpotifyError, clean_artist

GITHUB_API = "https://api.github.com"
DISCOGS_API = "https://api.discogs.com"
REPO = "LorenzoCavatorta/music-library-manager"
REPO_OWNER = REPO.split("/")[0]
COLLECTION_PATH = "collection.json"
SPOTIFY_ALBUM_RE = re.compile(r"https://open\.spotify\.com/album/[a-zA-Z0-9]+")


def is_from_owner(issue: dict) -> bool:
    return (issue.get("user") or {}).get("login", "").lower() == REPO_OWNER.lower()


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
    requests_ = []
    for i in issues:
        if not is_from_owner(i):
            print(f"Skipping #{i['number']}: not opened by {REPO_OWNER}")
            continue
        if any(l["name"] == "needs-attention" for l in i.get("labels", [])):
            continue
        requests_.append(i)
    return requests_


def fetch_release_details(discogs: requests.Session, release_id: int) -> dict | None:
    resp = discogs.get(f"{DISCOGS_API}/releases/{release_id}")
    if resp.status_code == 200:
        return resp.json()
    return None


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

    spotify_url = custom_fields.pop("SpotifyURL", None)
    if spotify_url:
        # Only accept real Spotify album links; normalize away query strings etc.
        valid = SPOTIFY_ALBUM_RE.match(spotify_url)
        spotify_url = valid.group(0) if valid else None
    if not spotify_url:
        match = re.search(r"https://open\.spotify\.com/album/[a-zA-Z0-9]+[\S]*", title)
        if match:
            spotify_url = SPOTIFY_ALBUM_RE.match(match.group(0)).group(0)
            title = title.replace(match.group(0), "").strip(" -–—?&")
    else:
        match = re.search(r"https://open\.spotify\.com/album/[a-zA-Z0-9]+[\S]*", title)
        if match:
            title = title.replace(match.group(0), "").strip(" -–—?&")

    return title.strip(), custom_fields, spotify_url


clean_discogs_artist = clean_artist


def get_spotify_album_info(sp: Spotify | None, spotify_url: str) -> tuple[str, str] | None:
    """Fetch artist and title from a Spotify album URL."""
    if sp is None:
        return None
    try:
        return sp.album_info(spotify_url)
    except SpotifyError as e:
        print(f"  Spotify lookup failed: {e}")
        return None


def get_spotify_url(sp: Spotify | None, artists: list[str], title: str, year: int | None) -> str | None:
    """Confident Spotify match for a release. None if not found or Spotify unavailable
    (the record is then picked up by the next enrich_spotify run)."""
    if sp is None:
        return None
    try:
        match = sp.find_album(artists, title, year)
    except SpotifyError as e:
        print(f"  Spotify search failed: {e}")
        return None
    return match["url"] if match else None


def load_collection() -> list[dict]:
    if os.path.exists(COLLECTION_PATH):
        with open(COLLECTION_PATH) as f:
            return json.load(f)
    return []


def save_collection(collection: list[dict]):
    with open(COLLECTION_PATH, "w") as f:
        json.dump(collection, f, indent=2, ensure_ascii=False)


def add_to_collection_json(
    release_info: dict, search_result: dict | None, custom_fields: dict, spotify_url: str | None,
):
    collection = load_collection()
    release_id = release_info["id"]

    if any(r["id"] == release_id for r in collection):
        print(f"  Already in collection.json")
        return

    artists = release_info.get("artists", release_info.get("artists_sort", []))
    if isinstance(artists, list) and artists and isinstance(artists[0], dict):
        artists = [a["name"] for a in artists]
    elif isinstance(artists, str):
        artists = [artists]

    labels = release_info.get("labels", [])
    if labels and isinstance(labels[0], dict):
        labels = [l["name"] for l in labels]

    formats = release_info.get("formats", [])
    if formats and isinstance(formats[0], dict):
        formats = [f["name"] for f in formats]

    images = release_info.get("images", [])
    if images:
        primary = next((img for img in images if img.get("type") == "primary"), images[0])
        cover_image = primary.get("uri", "")
        thumb = primary.get("uri150", "")
    elif search_result:
        cover_image = search_result.get("cover_image", "")
        thumb = search_result.get("thumb", "")
    else:
        cover_image = ""
        thumb = ""

    record = {
        "id": release_id,
        "title": release_info.get("title", ""),
        "artists": artists,
        "year": release_info.get("year", 0),
        "labels": labels,
        "formats": formats,
        "genres": release_info.get("genres", []),
        "styles": release_info.get("styles", []),
        "cover_image": cover_image,
        "thumb": thumb,
        "custom_fields": custom_fields,
    }
    if spotify_url:
        record["spotify_url"] = spotify_url

    collection.append(record)
    save_collection(collection)
    print(f"  Added to collection.json ({len(collection)} total)")


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

    try:
        sp = Spotify.from_env()
        if sp is None:
            print("::warning::Spotify credentials not set; albums will be added without Spotify links")
    except SpotifyError as e:
        sp = None
        print(f"::warning::{e}; albums will be added without Spotify links")

    failures = []

    for issue in issues:
        query, custom_fields, provided_spotify_url = parse_request(issue)
        print(f"\nProcessing #{issue['number']}: \"{query}\"")
        if provided_spotify_url:
            print(f"  Spotify URL provided: {provided_spotify_url}")
        if custom_fields:
            print(f"  Fields: {custom_fields}")

        if not query and provided_spotify_url:
            info = get_spotify_album_info(sp, provided_spotify_url)
            if info:
                query = f"{info[0]} - {info[1]}"
                print(f"  Resolved from Spotify: \"{query}\"")
            else:
                flag_issue(
                    gh, issue["number"],
                    f"Could not fetch album info from Spotify URL: {provided_spotify_url}\n\n"
                    f"Please also include artist and album title.",
                )
                failures.append(f"#{issue['number']}: failed to resolve Spotify URL")
                print(f"  Could not resolve Spotify URL")
                continue

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

            release_details = fetch_release_details(discogs, release_id)
            time.sleep(1)

            if provided_spotify_url:
                spotify_url = provided_spotify_url
            else:
                if release_details:
                    artist_names = [a["name"] for a in release_details.get("artists", [])]
                    album_title = release_details.get("title", "")
                    album_year = release_details.get("year") or None
                else:
                    parts = result.get("title", "").split(" - ", 1)
                    artist_names = [parts[0]] if len(parts) == 2 else []
                    album_title = parts[-1]
                    album_year = int(result["year"]) if str(result.get("year", "")).isdigit() else None
                spotify_url = get_spotify_url(sp, artist_names, album_title, album_year)

            if spotify_url:
                print(f"  Spotify: {spotify_url}")

            add_to_collection_json(
                release_details or result,
                result,
                custom_fields,
                spotify_url,
            )

            comment = (
                f"Added to collection: **{title}** ({year})\n\n"
                f"Discogs release: https://www.discogs.com/release/{release_id}\n"
            )
            if spotify_url:
                comment += f"Spotify: {spotify_url}\n"
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
