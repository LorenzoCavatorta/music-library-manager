"""Process 'add-request' GitHub issues: search Discogs, add to collection, update collection.json."""

import base64
import json
import os
import re
import sys
import time

import requests

GITHUB_API = "https://api.github.com"
DISCOGS_API = "https://api.discogs.com"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_SEARCH_URL = "https://api.spotify.com/v1/search"
REPO = "LorenzoCavatorta/music-library-manager"
COLLECTION_PATH = "collection.json"


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
    if not spotify_url:
        match = re.search(r"https://open\.spotify\.com/album/[a-zA-Z0-9]+[\S]*", title)
        if match:
            spotify_url = re.match(r"https://open\.spotify\.com/album/[a-zA-Z0-9]+", match.group(0)).group(0)
            title = title.replace(match.group(0), "").strip(" -–—?&")
    else:
        match = re.search(r"https://open\.spotify\.com/album/[a-zA-Z0-9]+[\S]*", title)
        if match:
            title = title.replace(match.group(0), "").strip(" -–—?&")

    return title.strip(), custom_fields, spotify_url


def get_spotify_album_info(spotify_url: str) -> tuple[str, str] | None:
    """Fetch artist and title from a Spotify album URL."""
    client_id = os.environ.get("SPOTIFY_CLIENT_ID")
    client_secret = os.environ.get("SPOTIFY_CLIENT_SECRET")
    if not client_id or not client_secret:
        return None

    resp = requests.post(
        SPOTIFY_TOKEN_URL,
        data={"grant_type": "client_credentials"},
        headers={
            "Authorization": "Basic "
            + base64.b64encode(f"{client_id}:{client_secret}".encode()).decode(),
        },
        timeout=(5, 10),
    )
    if resp.status_code != 200:
        return None

    token = resp.json()["access_token"]
    album_id = spotify_url.rstrip("/").split("/")[-1].split("?")[0]
    resp = requests.get(
        f"https://api.spotify.com/v1/albums/{album_id}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=(5, 10),
    )
    if resp.status_code != 200:
        return None

    data = resp.json()
    artist = data["artists"][0]["name"] if data.get("artists") else ""
    title = data.get("name", "")
    return artist, title


def clean_discogs_artist(name: str) -> str:
    return re.sub(r"\s*\(\d+\)$", "", name)


def get_spotify_url(artist: str, title: str) -> str | None:
    client_id = os.environ.get("SPOTIFY_CLIENT_ID")
    client_secret = os.environ.get("SPOTIFY_CLIENT_SECRET")
    if not client_id or not client_secret:
        return None

    artist = clean_discogs_artist(artist)

    resp = requests.post(
        SPOTIFY_TOKEN_URL,
        data={"grant_type": "client_credentials"},
        headers={
            "Authorization": "Basic "
            + base64.b64encode(f"{client_id}:{client_secret}".encode()).decode(),
        },
        timeout=(5, 10),
    )
    if resp.status_code != 200:
        return None

    token = resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    queries = [
        f"artist:{artist} album:{title}",
        f"{artist} {title}",
    ]
    for query in queries:
        resp = requests.get(
            SPOTIFY_SEARCH_URL,
            params={"q": query, "type": "album", "limit": 1},
            headers=headers,
            timeout=(5, 10),
        )
        if resp.status_code != 200:
            return None
        items = resp.json().get("albums", {}).get("items", [])
        if items:
            return items[0]["external_urls"].get("spotify")

    return None


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

    failures = []

    for issue in issues:
        query, custom_fields, provided_spotify_url = parse_request(issue)
        print(f"\nProcessing #{issue['number']}: \"{query}\"")
        if provided_spotify_url:
            print(f"  Spotify URL provided: {provided_spotify_url}")
        if custom_fields:
            print(f"  Fields: {custom_fields}")

        if not query and provided_spotify_url:
            info = get_spotify_album_info(provided_spotify_url)
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
                    artist_name = release_details["artists"][0]["name"] if release_details.get("artists") else ""
                    album_title = release_details.get("title", "")
                else:
                    parts = result.get("title", "").split(" - ", 1)
                    artist_name = parts[0] if len(parts) == 2 else ""
                    album_title = parts[-1]
                spotify_url = get_spotify_url(artist_name, album_title)

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
