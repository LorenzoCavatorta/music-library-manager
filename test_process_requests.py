"""Tests for parse_request and related helpers in process_requests."""

import pytest

from process_requests import clean_discogs_artist, parse_request


class TestParseRequest:
    def test_plain_text_query(self):
        issue = {"title": "Add: Radiohead - OK Computer", "body": ""}
        query, fields, url = parse_request(issue)
        assert query == "Radiohead - OK Computer"
        assert url is None
        assert fields == {}

    def test_text_with_custom_fields(self):
        issue = {
            "title": "Add: TEED - Trouble",
            "body": "### Custom fields\n\n- **Feeling:** Energy\n- **Rating:** 4",
        }
        query, fields, url = parse_request(issue)
        assert query == "TEED - Trouble"
        assert fields == {"Feeling": "Energy", "Rating": "4"}
        assert url is None

    def test_spotify_url_in_body(self):
        issue = {
            "title": "Add: Radiohead - OK Computer",
            "body": "### Custom fields\n\n- **Feeling:** Melancholic\n- **SpotifyURL:** https://open.spotify.com/album/6dVIqQ8qmQ5GBnJ9shOYGE",
        }
        query, fields, url = parse_request(issue)
        assert query == "Radiohead - OK Computer"
        assert url == "https://open.spotify.com/album/6dVIqQ8qmQ5GBnJ9shOYGE"
        assert "SpotifyURL" not in fields

    def test_spotify_url_only_in_title(self):
        issue = {
            "title": "Add: https://open.spotify.com/album/6xuXmpSyh7WqIct3bvsSfg?si=abc123",
            "body": "",
        }
        query, fields, url = parse_request(issue)
        assert query == ""
        assert url == "https://open.spotify.com/album/6xuXmpSyh7WqIct3bvsSfg"

    def test_spotify_url_in_title_and_body(self):
        issue = {
            "title": "Add: https://open.spotify.com/album/6xuXmpSyh7WqIct3bvsSfg?si=VL7LoAA",
            "body": "### Custom fields\n\n- **Feeling:** Frozen\n- **SpotifyURL:** https://open.spotify.com/album/6xuXmpSyh7WqIct3bvsSfg",
        }
        query, fields, url = parse_request(issue)
        assert query == ""
        assert url == "https://open.spotify.com/album/6xuXmpSyh7WqIct3bvsSfg"
        assert "SpotifyURL" not in fields

    def test_text_plus_spotify_url_in_title(self):
        issue = {
            "title": "Add: Radiohead https://open.spotify.com/album/6dVIqQ8qmQ5GBnJ9shOYGE",
            "body": "",
        }
        query, fields, url = parse_request(issue)
        assert query == "Radiohead"
        assert url == "https://open.spotify.com/album/6dVIqQ8qmQ5GBnJ9shOYGE"

    def test_prefix_variations(self):
        for prefix in ("Add:", "add:", "Add ", "add "):
            issue = {"title": f"{prefix} Some Album", "body": ""}
            query, _, _ = parse_request(issue)
            assert query == "Some Album"


class TestCleanDiscogsArtist:
    def test_strips_disambiguation_suffix(self):
        assert clean_discogs_artist("tUnE-yArDs (2)") == "tUnE-yArDs"
        assert clean_discogs_artist("The Beatles (3)") == "The Beatles"

    def test_leaves_normal_names(self):
        assert clean_discogs_artist("Radiohead") == "Radiohead"
        assert clean_discogs_artist("Godspeed You! Black Emperor") == "Godspeed You! Black Emperor"

    def test_leaves_parentheses_that_arent_disambiguation(self):
        assert clean_discogs_artist("Sunn O)))") == "Sunn O)))"
        assert clean_discogs_artist("The (International) Noise Conspiracy") == "The (International) Noise Conspiracy"
