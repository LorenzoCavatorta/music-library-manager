"""Shared Spotify helpers: auth, album lookup, and confident album matching.

Search results are scored on artist + title similarity instead of taking the
first hit, so we never store a link to a different album by the same artist
(e.g. "Ye" -> "Yeezus") or to an unrelated artist with a similar name.
"""

import base64
import os
import re
import time
import unicodedata
from difflib import SequenceMatcher

import requests

TOKEN_URL = "https://accounts.spotify.com/api/token"
API = "https://api.spotify.com/v1"
TIMEOUT = (5, 10)

MIN_ARTIST_SIM = 0.8
MIN_TITLE_SIM = 0.85
# Words that mark a variant release; penalised unless the record title has them too.
VARIANT_RE = re.compile(r"\b(remix(es|ed)?|mix(es)?|vip|live|instrumentals?|karaoke|acoustic|edits?|demos?|commentary)\b", re.I)


class SpotifyError(Exception):
    """Transient/API failure. Callers should retry later, not treat it as 'not found'."""


def load_dotenv(path: str = ".env"):
    """Load KEY=VALUE lines from a local .env without overriding real env vars."""
    if not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip("'\""))


class Spotify:
    def __init__(self, client_id: str, client_secret: str):
        self.session = requests.Session()
        resp = requests.post(
            TOKEN_URL,
            data={"grant_type": "client_credentials"},
            headers={"Authorization": "Basic " + base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()},
            timeout=TIMEOUT,
        )
        if resp.status_code != 200:
            raise SpotifyError(f"Spotify auth failed: {resp.status_code} {resp.text[:200]}")
        self.session.headers["Authorization"] = f"Bearer {resp.json()['access_token']}"

    @classmethod
    def from_env(cls) -> "Spotify | None":
        load_dotenv()
        client_id = os.environ.get("SPOTIFY_CLIENT_ID")
        client_secret = os.environ.get("SPOTIFY_CLIENT_SECRET")
        if not client_id or not client_secret:
            return None
        return cls(client_id, client_secret)

    def _get(self, path: str, params: dict | None = None) -> dict:
        for _ in range(3):
            try:
                resp = self.session.get(f"{API}{path}", params=params, timeout=TIMEOUT)
            except requests.RequestException as e:
                raise SpotifyError(f"request failed: {e}") from e
            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", 5))
                if retry_after > 60:
                    raise SpotifyError(f"rate limited for {retry_after}s")
                print(f"  Rate limited, waiting {retry_after}s...")
                time.sleep(retry_after)
                continue
            if resp.status_code != 200:
                raise SpotifyError(f"GET {path} -> {resp.status_code}")
            return resp.json()
        raise SpotifyError("rate limited repeatedly")

    def album_info(self, album_url: str) -> tuple[str, str] | None:
        """(artist, title) for a Spotify album URL, or None if it doesn't exist."""
        album_id = album_url.rstrip("/").split("/")[-1].split("?")[0]
        try:
            data = self._get(f"/albums/{album_id}")
        except SpotifyError as e:
            if "-> 404" in str(e) or "-> 400" in str(e):
                return None
            raise
        artist = data["artists"][0]["name"] if data.get("artists") else ""
        return artist, data.get("name", "")

    def find_album(self, artists: list[str], title: str, year: int | None = None) -> dict | None:
        """Best confident match for a release, or None if nothing matches well enough.

        Returns {"url", "name", "artists", "album_type", "score"}. Raises SpotifyError on API failure.
        """
        artists = [clean_artist(a) for a in artists if a] or [""]
        title = title.strip()
        queries = [f"artist:{artists[0]} album:{title}", f"{artists[0]} {title}"]
        if strip_parens(title) != title:
            queries.append(f"{artists[0]} {strip_parens(title)}")
        for extra in artists[1:3]:
            queries.append(f"{extra} {title}")

        best, seen = None, set()
        for query in queries:
            items = self._get("/search", {"q": query, "type": "album", "limit": 10}).get("albums", {}).get("items", [])
            for item in items:
                if not item or item["id"] in seen:
                    continue
                seen.add(item["id"])
                s = score_candidate(artists, title, year, item)
                if s is not None and (best is None or s > best["score"]):
                    best = {
                        "url": item["external_urls"]["spotify"],
                        "name": item["name"],
                        "artists": [a["name"] for a in item.get("artists", [])],
                        "album_type": item.get("album_type", ""),
                        "score": round(s, 3),
                    }
            if best and best["score"] >= 2.0:  # exact artist + title match; no need for more queries
                break
            time.sleep(0.1)
        return best


def clean_artist(name: str) -> str:
    """Strip Discogs disambiguation suffixes: 'Grimes (4)' -> 'Grimes'."""
    return re.sub(r"\s*\(\d+\)$", "", name).strip()


def strip_parens(s: str) -> str:
    return re.sub(r"\s*[\(\[][^)\]]*[\)\]]", "", s).strip()


EDITION_RE = re.compile(
    r"[\(\[][^)\]]*\b(edition|remaster(ed)?|deluxe|version|expanded|anniversary|bonus|reissue)\b[^)\]]*[\)\]]"
)


# "(feat. X)", "[with X]", " ft. X" — credits, not part of the title.
FEAT_RE = re.compile(r"[\(\[]\s*(feat|ft|featuring|with)\b[^)\]]*[\)\]]|\s(feat|ft|featuring)\.?\s.*$")


def words(s: str) -> list[str]:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    s = clean_artist(s)
    s = FEAT_RE.sub(" ", s)
    s = EDITION_RE.sub(" ", s)
    s = s.replace("&", " and ")
    return [w for w in re.split(r"[^a-z0-9]+", s) if w and w not in ("the", "a", "and")]


ROMAN = {"ii": "2", "iii": "3", "iv": "4", "vi": "6", "vii": "7", "viii": "8", "ix": "9"}


def numbers(ws: list[str]) -> list[str]:
    """Numbers in a title, including roman numerals (ambiguous single letters i/v/x excluded)."""
    out = []
    for w in ws:
        out += re.findall(r"\d+", w)
        if w in ROMAN:
            out.append(ROMAN[w])
    return out


def similarity(a: str, b: str) -> float:
    wa, wb = words(a), words(b)
    ja, jb = "".join(wa), "".join(wb)
    if not ja or not jb:
        return 0.0
    if ja == jb:  # "EP3" == "EP 3", "Bon Iver, Bon Iver" == "Bon Iver Bon Iver"
        return 1.0
    if numbers(wa) != numbers(wb):  # "Run The Jewels" vs "Run The Jewels 2", "Carter II" vs "Carter III"
        return 0.0
    short, long_ = (wa, wb) if len(ja) <= len(jb) else (wb, wa)
    n = len(short)
    if len("".join(short)) >= 4 and any(long_[i:i + n] == short for i in range(len(long_) - n + 1)):
        return 0.85  # whole-word containment, e.g. "Teenage Dream" in "Teenage Dream: The Complete Confection"
    if min(len(ja), len(jb)) < 5:  # short titles must match exactly ("On" != "One", "Me" != "Save Me")
        return 0.0
    return SequenceMatcher(None, ja, jb).ratio()


def variant_words(s: str) -> set[str]:
    s = FEAT_RE.sub(" ", s or "")
    return {re.sub(r"(es|ed|s)$", "", m.group(0).lower()) for m in VARIANT_RE.finditer(s)}


def score_candidate(artists: list[str], title: str, year: int | None, item: dict) -> float | None:
    cand_artists = [a["name"] for a in item.get("artists", [])]
    a = max((similarity(x, y) for x in artists for y in cand_artists), default=0.0)
    t = similarity(title, item.get("name", ""))
    if a < MIN_ARTIST_SIM or t < MIN_TITLE_SIM:
        return None
    # A remix/live/instrumental release is a different record from the original (either way round).
    if variant_words(title) != variant_words(item.get("name", "")):
        return None
    s = a + t
    if item.get("album_type") == "album":
        s += 0.05
    release_year = (item.get("release_date") or "")[:4]
    if year and release_year.isdigit():
        s -= min(abs(int(release_year) - year), 20) * 0.005
    return s
