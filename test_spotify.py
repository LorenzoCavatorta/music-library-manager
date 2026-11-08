"""Matching tests, using real mismatches found in the collection audit."""

from spotify import score_candidate, similarity


def album(name, artist, album_type="album", release_date="2000"):
    return {"name": name, "artists": [{"name": artist}], "album_type": album_type, "release_date": release_date}


class TestSimilarity:
    def test_equivalent_titles(self):
        assert similarity("EP3", "EP 3") == 1.0
        assert similarity("Bon Iver, Bon Iver", "Bon Iver Bon Iver") == 1.0
        assert similarity("Tourist History Deluxe Edition", "Tourist History (Deluxe Edition)") >= 0.85
        assert similarity("Born To Die", "Born To Die (Deluxe Version)") == 1.0
        assert similarity("Sigur Rós", "Sigur Ros") == 1.0
        assert similarity("Grimes (4)", "Grimes") == 1.0

    def test_different_numbers_dont_match(self):
        assert similarity("Run The Jewels", "Run The Jewels 2") == 0.0
        assert similarity("Tha Carter II", "Tha Carter III") < 0.8
        assert similarity("Never Stop", "Never Stop II") < 0.8

    def test_short_titles_must_be_exact(self):
        assert similarity("Ye", "Yeezus") < 0.8
        assert similarity("Me", "Save Me") < 0.8
        assert similarity("On", "One") < 0.8
        assert similarity("i,i", "Bon Iver, Bon Iver") < 0.8

    def test_partial_words_dont_match(self):
        assert similarity("Blood", "Bloody Knives") < 0.8
        assert similarity("Low", "All Time Low") < 0.8
        assert similarity("Arca", "the arcade boy") < 0.8

    def test_whole_word_containment_is_a_weak_match(self):
        assert similarity("Teenage Dream", "Teenage Dream: The Complete Confection") == 0.85


class TestScoreCandidate:
    def test_rejects_wrong_artist(self):
        assert score_candidate(["Low"], "C'mon", 2011, album("Monsters (Prblm Chld Remix)", "All Time Low")) is None
        assert score_candidate(["Bonnie \"Prince\" Billy"], "New Black Rich (Tusks)", 2009, album("Gold", "Tusks")) is None

    def test_prefers_album_over_remix_single(self):
        orig = score_candidate(["Jessie Ware"], "What's Your Pleasure?", 2020, album("What's Your Pleasure?", "Jessie Ware", release_date="2020"))
        remix = score_candidate(["Jessie Ware"], "What's Your Pleasure?", 2020, album("What’s Your Pleasure? (Tobtok Remix)", "Jessie Ware", "single", "2020"))
        assert remix is None or orig > remix

    def test_prefers_exact_album_over_single_containing_title(self):
        exact = score_candidate(["Jens Lekman"], "Night Falls Over Kortedala", 2007, album("Night Falls Over Kortedala", "Jens Lekman", release_date="2007"))
        single = score_candidate(["Jens Lekman"], "Night Falls Over Kortedala", 2007, album("The Linden Trees Are Still In Blossom (Night Falls Over Kortedala)", "Jens Lekman", "single", "2007"))
        assert exact > single

    def test_feat_credits_are_not_title(self):
        # self-titled album must not match a single that merely features the artist
        assert score_candidate(["Christine And The Queens"], "Christine And The Queens", 2015,
                               album("The Only One (feat. Christine and the Queens)", "Christine and the Queens", "single")) is None

    def test_variant_mismatch_rejected_both_ways(self):
        assert score_candidate(["Arctic Monkeys"], "Favourite Worst Nightmare Instrumentals", 2007, album("Favourite Worst Nightmare", "Arctic Monkeys")) is None
        assert score_candidate(["Stephan Bodzin"], "Luna", 2011, album("Luna (The Remixes)", "Stephan Bodzin", "single")) is None
        assert score_candidate(["AlunaGeorge"], "Body Music (Remixed)", 2014, album("Body Music (Remixes)", "AlunaGeorge")) is not None

    def test_similar_but_different_title_rejected(self):
        assert score_candidate(["Fred Buscaglione"], "Criminalmente Fred", 1992, album("Criminalmente bella", "Fred Buscaglione", "single")) is None

    def test_matches_featured_artist_records(self):
        s = score_candidate(["These Hidden Hands", "Lucrecia Dalt"], "These Moments Dismantled", 2017, album("These Moments Dismantled", "These Hidden Hands"))
        assert s is not None
