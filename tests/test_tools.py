"""Offline tests (no API key needed):  pytest -q"""
from carnatic.catalog import Catalog
from carnatic.profile import ProfileStore
from carnatic.tools import Toolbox


def make(tmp_path):
    return Toolbox(Catalog.load(), ProfileStore(tmp_path / "p.db"), "u1")


def test_catalogue_loads_and_validates():
    cat = Catalog.load()
    assert len(cat.raagas) >= 30 and len(cat.krithis) >= 50 and len(cat.moods) >= 10


def test_spelling_variants(tmp_path):
    tb = make(tmp_path)
    for name in ["Sankarabharanam", "dheerasankarabharanam", "Todi", "Hamsadhvani", "kamboji"]:
        assert tb.run("lookup_raaga", {"name": name})["found"], name


def test_unknown_raaga(tmp_path):
    assert make(tmp_path).run("lookup_raaga", {"name": "Zorbulu"})["found"] is False


def test_krithi_search(tmp_path):
    r = make(tmp_path).run("search_krithis", {"title": "vatapi"})
    assert r["krithis"][0]["raaga"] == "Hamsadhwani"


def test_recommend_respects_dislikes(tmp_path):
    tb = make(tmp_path)
    before = [x["raaga"] for x in tb.run("recommend", {"moods": ["sit_with_sadness"]})["recommendations"]]
    assert "Thodi" in before
    tb.run("record_feedback", {"item_type": "raaga", "item_name": "Thodi", "signal": -1})
    after = [x["raaga"] for x in tb.run("recommend", {"moods": ["sit_with_sadness"]})["recommendations"]]
    assert "Thodi" not in after


def test_recommend_boosts_likes_and_language(tmp_path):
    tb = make(tmp_path)
    tb.run("record_feedback", {"item_type": "raaga", "item_name": "Kapi", "signal": 1})
    tb.run("set_preference", {"key": "languages", "value": ["Tamil"]})
    recs = tb.run("recommend", {"moods": ["romantic_nostalgic"]})["recommendations"]
    assert recs[0]["raaga"] == "Kapi"
    assert recs[0]["krithis"][0]["language"] == "Tamil"


def test_change_of_mind(tmp_path):
    tb = make(tmp_path)
    tb.run("record_feedback", {"item_type": "raaga", "item_name": "Thodi", "signal": -1})
    tb.run("record_feedback", {"item_type": "raaga", "item_name": "Thodi", "signal": 1})
    prof = tb.profiles.get("u1")
    assert "Thodi" in prof["likes"]["raaga"] and "Thodi" not in prof["dislikes"]["raaga"]


def test_avoid_moods_enforced(tmp_path):
    tb = make(tmp_path)
    for mood, banned in [("light_playful", "Thodi"), ("energise_motivate", "Shanmukhapriya"),
                         ("sit_with_sadness", "Natabhairavi"), ("joyful_celebrate", "Abheri"),
                         ("sit_with_sadness", "Begada")]:
        recs = [x["raaga"] for x in tb.run("recommend", {"moods": [mood], "limit": 6})["recommendations"]]
        assert banned not in recs, (mood, banned)


def test_primary_mood_ranks_first(tmp_path):
    recs = make(tmp_path).run("recommend", {"moods": ["devotional_reflective"], "limit": 6})["recommendations"]
    assert all("primary" in r["why"][0] for r in recs[:3])


def test_expert_corrections(tmp_path):
    tb = make(tmp_path)
    assert tb.run("search_krithis", {"title": "Marivere Dikkevvaru"})["krithis"][0]["raaga"] == "Lathangi"
    assert tb.run("search_krithis", {"title": "Sri Valli Devasenapathe"})["krithis"][0]["language"] == "Sanskrit"
    r = tb.run("lookup_raaga", {"name": "Vasantha"})["raaga"]
    assert r["melakarta_number"] == 15 and "17 Suryakantam" in r["alternate_parents"]
    assert tb.run("lookup_raaga", {"name": "Karnataka Devagandhari"})["found"] is False


def test_validation_rejects_tag_avoid_clash():
    import pytest
    cat = Catalog.load()
    cat.raagas["Thodi"].avoid_moods.append("devotional_reflective")
    with pytest.raises(ValueError):
        cat.validate()


def test_krithi_level_moods(tmp_path):
    tb = make(tmp_path)
    # Vasantha qualifies for energise through Paramapurusha, which should be the krithi shown
    recs = {x["raaga"]: x for x in tb.run("recommend", {"moods": ["energise_motivate"], "limit": 10})["recommendations"]}
    assert recs["Vasantha"]["krithis"][0]["title"] == "Paramapurusha"
    assert recs["Kadanakuthuhalam"]["krithis"][0]["title"] == "Raghuvamsa Sudha"
    # Vallinayakane is explicitly not energetic, Shanmukhapriya never appears for energise
    assert "Shanmukhapriya" not in recs


def test_favourites_resolve():
    cat = Catalog.load()
    from seed_profile import FAVOURITES
    for t in FAVOURITES["pranav"]:
        assert cat.krithis_for(title=t), t
    for q in ["Vathapi Ganapathim", "Endaromahanubhavulu", "Kadanakuthuhala", "Naata", "Hamsanada"]:
        assert cat.krithis_for(title=q) or cat.resolve_raaga(q), q


def test_every_krithi_has_tala():
    assert all(k.tala for k in Catalog.load().krithis)


def test_intense_dramatic_bucket(tmp_path):
    recs = [x["raaga"] for x in make(tmp_path).run("recommend", {"moods": ["intense_dramatic"], "limit": 6})["recommendations"]]
    assert {"Shanmukhapriya", "Lathangi", "Shubhapantuvarali"} <= set(recs)
    # Thodi is tagged intense as a raaga, but none of its catalogue songs is: no fitting song, no suggestion.
    assert "Thodi" not in recs


def test_every_row_has_a_source():
    cat = Catalog.load()
    assert all(r.sources and r.sources[0].startswith("https://") for r in cat.raagas.values())
    assert all(k.sources and k.sources[0].startswith("https://") for k in cat.krithis)


def test_source_backed_fixes():
    k = {x.title: x for x in Catalog.load().krithis}
    assert k["Rama Nee Samanamevaru"].tala == "Rupaka"
    assert k["Pakkala Nilabadi"].tala == "Misra Chapu"
    assert k["Palinchu Kamakshi"].tala == "Adi"
    assert k["Jagadanandakaraka"].language == "Sanskrit"


def test_reviewer_decisions():
    k = {x.title: x for x in Catalog.load().krithis}
    assert k["Manasuloni"].raaga == "Hindolam" and "Varamu" in k["Manasuloni"].notes
    assert k["Emi Jesite"].tala == "Misra Chapu"
    assert k["Venkatachala Nilayam"].language == "Sanskrit"



def test_song_must_fit_the_mood(tmp_path):
    """Regression: 'upbeat in Kannada' suggested Jagadoddharana (a soothing song) because its raaga, Kapi, is tagged
    light/playful. A song is suggested only for moods it is tagged with."""
    tb = make(tmp_path)
    tb.run("set_preference", {"key": "languages", "value": ["Kannada"]})
    for moods in (["light_playful"], ["energise_motivate", "joyful_celebrate"]):
        titles = [k["title"] for r in tb.run("recommend", {"moods": moods, "limit": 10})["recommendations"] for k in r["krithis"]]
        assert "Jagadoddharana" not in titles
    cat = tb.cat
    for mood in cat.moods:
        res = tb.run("recommend", {"moods": [mood], "limit": 10})
        want = res["closest_match"]["used_mood"] if "closest_match" in res else mood   # labelled fallback
        for r in res["recommendations"]:
            for k in r["krithis"]:
                assert want in next(x for x in cat.krithis if x.title == k["title"]).moods, (mood, k["title"])


def test_closest_mood_fallback(tmp_path):
    """Owner-approved map: fall back only when NO song has the mood; label it; never across avoid rules;
    a language miss does not fall back; sit_with_sadness is never cheered up."""
    tb = make(tmp_path)
    cat = tb.cat
    r = tb.run("recommend", {"moods": ["fresh_morning"]})             # owner tagged morning songs: no fallback
    assert "closest_match" not in r and r["recommendations"][0]["krithis"][0]["title"] == "Sriman Narayana"
    sleepy = [k.title for k in cat.krithis if "wind_down_sleep" in k.moods]
    for t in sleepy:                                                   # note every sleep song as not sleepy for me
        tb.run("report_correction", {"item_type": "krithi", "item_name": t, "remove_moods": ["wind_down_sleep"], "reason": "x"})
    r = tb.run("recommend", {"moods": ["wind_down_sleep"]})           # now no song fits sleep for this user
    assert r["closest_match"]["used_mood"] == "calm_anxious" and r["recommendations"]
    for p in r["recommendations"]:
        assert "wind_down_sleep" not in cat.raagas[p["raaga"]].avoid_moods
        assert all(k["title"] not in sleepy for k in p["krithis"])
    r = tb.run("recommend", {"moods": ["joyful_celebrate"]})
    assert "closest_match" not in r
    r = tb.run("recommend", {"moods": ["sit_with_sadness"], "language": "Kannada"})
    assert not r["recommendations"] and "closest_match" not in r and "other languages" in r["note"]
    r = tb.run("recommend", {"moods": ["romantic_nostalgic"], "language": "Kannada"})
    assert len(r["recommendations"]) == 1 and r["note"].startswith("Only 1")
    assert not set(cat.moods["sit_with_sadness"].fallback) & {"comfort_when_low", "joyful_celebrate", "energise_motivate", "light_playful"}


def test_language_filter(tmp_path):
    tb = make(tmp_path)
    r = tb.run("recommend", {"moods": ["energise_motivate", "joyful_celebrate"], "language": "Kannada"})
    assert [k["title"] for x in r["recommendations"] for k in x["krithis"]] == ["Odi Baarayya"]
    empty = tb.run("recommend", {"moods": ["light_playful"], "language": "Kannada"})
    assert empty["recommendations"] == [] and "No song in the catalogue fits" in empty["note"]


def test_mood_correction_is_personal_and_queued(tmp_path):
    from carnatic.proposals import ProposalStore
    import shutil
    from carnatic.catalog import DATA_DIR
    shutil.copytree(DATA_DIR, tmp_path / "data")
    cat = Catalog.load(tmp_path / "data")
    ps = ProposalStore(tmp_path / "p.db", tmp_path / "data")
    me = Toolbox(cat, ProfileStore(tmp_path / "me.db"), "me", ps)
    other = Toolbox(cat, ProfileStore(tmp_path / "other.db"), "other", ps)
    res = me.run("report_correction", {"item_type": "krithi", "item_name": "Kaddanu Variki",
                                       "remove_moods": ["grand_uplifted"], "reason": "too intimate to feel grand"})
    assert res["proposal"]["status"] == "pending curator approval"
    titles = lambda tb: [k["title"] for r in tb.run("recommend", {"moods": ["grand_uplifted"], "limit": 10})["recommendations"] for k in r["krithis"]]
    assert "Kaddanu Variki" not in titles(me)            # applies to me at once
    assert "Kaddanu Variki" in titles(other)            # nobody else, until approved
    assert not me.run("record_feedback", {"item_type": "krithi", "item_name": "x", "signal": 1}).get("error")
    assert ps.approve(res["proposal"]["proposal_id"])["status"] == "approved"
    k = next(x for x in Catalog.load(tmp_path / "data").krithis if x.title == "Kaddanu Variki")
    assert "grand_uplifted" not in k.moods and "grand_uplifted" in k.avoid_moods


def test_additions_need_trusted_sources_and_evidence(tmp_path):
    from carnatic.proposals import ProposalStore
    import shutil
    from carnatic.catalog import DATA_DIR
    shutil.copytree(DATA_DIR, tmp_path / "data")
    cat = Catalog.load(tmp_path / "data")
    ps = ProposalStore(tmp_path / "p.db", tmp_path / "data")
    tb = Toolbox(cat, ProfileStore(tmp_path / "u.db"), "u", ps)
    rec = {"title": "Zz Bhajare Test", "raaga": "Abheri", "composer": "Mysore Vasudevachar", "language": "Sanskrit", "tala": "Adi"}
    ev = "Karnatik.com Abheri page lists: bhajarE rE maanasa - aadi - Mysore VaasudEvaacaarya"
    assert "error" in tb.run("propose_addition", {"kind": "krithi", "record": rec, "sources": ["https://example.com/x"], "evidence": ev})
    assert "error" in tb.run("propose_addition", {"kind": "krithi", "record": rec, "sources": ["http://karnatik.com/c1256.shtml"], "evidence": ev})
    assert "error" in tb.run("propose_addition", {"kind": "krithi", "record": rec, "sources": ["https://karnatik.com/c1256.shtml"], "evidence": "trust me"})
    assert "error" in tb.run("propose_addition", {"kind": "krithi", "record": {**rec, "raaga": "Varali"}, "sources": ["https://karnatik.com/c1256.shtml"], "evidence": ev})
    assert "error" in tb.run("propose_addition", {"kind": "krithi", "record": {**rec, "title": "Nagumomu"}, "sources": ["https://karnatik.com/c1256.shtml"], "evidence": ev})
    src = ["https://karnatik.com/c1256.shtml"]
    dev = {"kind": "krithi", "record": {**rec, "moods": ["devotional_reflective"]}, "sources": src, "evidence": ev}
    # Moods need evidence (owner's rule): none, an untrusted page, an empty quote, or evidence for another mood all fail.
    assert "no basis" in tb.run("propose_addition", dev)["error"]
    assert "error" in tb.run("propose_addition", {**dev, "mood_evidence": [{"mood": "devotional_reflective", "source": "https://example.com/x", "quote": "a prayer song to Rama, sung with devotion"}]})
    assert "error" in tb.run("propose_addition", {**dev, "mood_evidence": [{"mood": "devotional_reflective", "source": src[0], "quote": "yes"}]})
    assert "error" in tb.run("propose_addition", {**dev, "mood_evidence": [{"mood": "devotional_reflective", "source": "user", "quote": "so devotional"},
                                                                          {"mood": "joyful_celebrate", "source": "user", "quote": "happy"}]})
    meaning = {"mood": "devotional_reflective", "source": "https://www.shivkumar.org/music/bhajare-re-manasa.htm",
               "quote": "Worship, O mind, Sri Raghuvira, who grants worldly joy and liberation", "about": "song"}
    # Inferred from the meaning, but the user hasn't validated it yet: refused.
    assert "user_confirmed" in tb.run("propose_addition", {**dev, "mood_evidence": [meaning]})["error"]
    ok = tb.run("propose_addition", {**dev, "mood_evidence": [{**meaning, "user_confirmed": True}]})
    assert ok["status"] == "pending curator approval"
    assert not [k for k in Catalog.load(tmp_path / "data").krithis if k.title == "Zz Bhajare Test"]   # not until approved
    assert ps.approve(ok["proposal_id"])["status"] == "approved"
    k = next(k for k in Catalog.load(tmp_path / "data").krithis if k.title == "Zz Bhajare Test")
    assert k.raaga == "Abheri" and k.verified is False and k.moods == ["devotional_reflective"]
    assert k.sources == ["https://karnatik.com/c1256.shtml", "https://www.shivkumar.org/music/bhajare-re-manasa.htm"]
    assert "proposal #" in k.notes and "Moods from: devotional_reflective (inferred from" in k.notes and "user-confirmed" in k.notes
    # No moods at all is fine: the curator sets them.
    assert tb.run("propose_addition", {"kind": "krithi", "record": {**rec, "title": "Some Other Song"}, "sources": src, "evidence": ev})["status"] == "pending curator approval"


def test_bad_approval_rolls_back(tmp_path):
    from carnatic.proposals import ProposalStore
    import shutil
    from carnatic.catalog import DATA_DIR
    shutil.copytree(DATA_DIR, tmp_path / "data")
    before = (tmp_path / "data" / "krithis.csv").read_text()
    ps = ProposalStore(tmp_path / "p.db", tmp_path / "data")
    pid = ps._add("u", "add_krithi", {"record": {"title": "Ghost", "raaga": "Nonexistent", "composer": "x", "language": "y"},
                                      "sources": ["https://karnatik.com/c1.shtml"], "evidence": "x" * 30})
    assert "error" in ps.approve(pid)
    assert (tmp_path / "data" / "krithis.csv").read_text() == before
    assert ps.get(pid)["status"] == "pending"


def test_agent_cannot_approve():
    from carnatic.catalog import Catalog as C
    names = {t["name"] for t in Toolbox(C.load(), ProfileStore(":memory:"), "u").schemas}
    assert not {n for n in names if "approve" in n or "reject" in n}


def test_similar_titles_explain_mixups(tmp_path):
    r = make(tmp_path).run("search_krithis", {"title": "Marivere Dikkevvaru"})
    assert r["krithis"][0]["raaga"] == "Lathangi"
    sim = {s["title"]: s["raaga"] for s in r["similar_titles"]}
    assert sim.get("Marivere Dikkevarayya") == "Shanmukhapriya"


def test_ragamalika_is_a_song_raaga_not_a_catalogue_row():
    """Owner's rule (21 Nov 2026): no Ragamalika row in raagas.csv; its songs still work."""
    from carnatic.catalog import RAGAMALIKA, is_ragamalika
    cat = Catalog.load()
    assert not any(is_ragamalika(r) for r in cat.raagas)
    assert any(k.title == "Kurai Onrum Illai" and k.raaga == RAGAMALIKA for k in cat.krithis)
    tb = Toolbox(cat, ProfileStore(":memory:"), "u")
    look = tb.run("lookup_raaga", {"name": "raagamaalika"})
    assert look["found"] is False and look["ragamalika"] and "Kurai Onrum Illai" in look["krithis_in_catalogue"]
    rec = tb.run("recommend", {"moods": ["fresh_morning"], "limit": 10})
    groups = rec["recommendations"] if isinstance(rec, dict) and "recommendations" in rec else rec
    assert any(g["raaga"] == RAGAMALIKA and g["krithis"][0]["title"] == "Kurai Onrum Illai" for g in groups)


def test_listen_links_come_with_every_song(tmp_path):
    """Owner's request (21 Nov 2026): when a user wants to hear a song, links are given at once."""
    tb = make(tmp_path)
    rec = tb.run("recommend", {"moods": ["grand_uplifted"], "limit": 2})["recommendations"]
    k = rec[0]["krithis"][0]
    assert [l["site"] for l in k["listen"]] == ["YouTube"]
    assert "youtube.com/results?search_query=" in k["listen"][0]["url"]
    found = tb.run("search_krithis", {"title": "Nidhi Chala"})["krithis"][0]
    assert found["listen"][0]["url"].endswith("Nidhi+Chala+Sukhama+Kalyani+Tyagaraja")
    out = tb.run("listen_links", {"title": "Laali Laaliyani", "raaga": "Harikambhoji", "composer": "Tyagaraja"})
    assert out["links"] == [{"site": "YouTube", "url": "https://www.youtube.com/results?search_query=Laali+Laaliyani+Harikambhoji+Tyagaraja"}]
    # Fact-checking links: only link types checked to work (no site: searches, no Rasikas forum search).
    urls = [l["url"] for l in tb.run("source_links", {"query": "Nidhi Chala Sukhama"})["links"]]
    assert all("site%3A" not in u and "search.php" not in u for u in urls)
