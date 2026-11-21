"""Background curator: gap finding, candidate checks, and adding to the suggestion box like the page does."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from build_web import build  # noqa: E402
from carnatic.catalog import Catalog  # noqa: E402
from carnatic.curator import AGENT, find_twin, run_add, run_check  # noqa: E402
from carnatic.gaps import find_gaps, load_config  # noqa: E402

SRC = "https://www.karnatik.com/c9999.shtml"
QUOTE = {"mood": "wind_down_sleep", "source": SRC, "quote": "a lullaby rocking the child Krishna gently to sleep",
         "about": "song", "needs_curator_confirmation": True}


def cand(**over):
    rec = {"title": "Zz Test Lullaby", "raaga": "Neelambari", "composer": "Test Composer", "language": "Tamil",
           "tala": "Adi", "form": "krithi", "moods": ["wind_down_sleep"]}
    rec.update(over.pop("record", {}))
    c = {"type": "addition", "kind": "krithi", "name": rec["title"], "record": rec, "sources": [SRC],
         "evidence": "raagam: neelaambari taaLam: aadi Composer: Test Composer", "mood_evidence": [QUOTE],
         "details": "Found for the gap: Wind down / sleep."}
    c.update(over)
    return c


@pytest.fixture
def cat():
    return Catalog.load()


def test_gaps_rank_moods_first(cat):
    gaps = find_gaps(cat, {**load_config(), "songs_per_mood": 6})
    assert gaps[0]["kind"] == "mood"
    sleep = next(g for g in gaps if g["key"] == "wind_down_sleep")
    assert sleep["have"] < sleep["target"] and "Neelambari" in sleep["hint_raagas"]
    kinds = [g["kind"] for g in gaps]
    assert kinds == sorted(kinds, key=["mood", "language", "raaga"].index)


def test_check_accepts_a_complete_candidate(cat):
    (r,) = run_check(cat, [cand()], {"items": []}, {"decisions": {}})
    assert r["ok"], r["problems"]


@pytest.mark.parametrize("bad, expect", [
    (dict(record={"tala": ""}), "missing"),
    (dict(sources=["https://example.com/x"]), "trusted"),
    (dict(evidence="short"), "evidence"),
    (dict(record={"raaga": "Zorbulu"}), "not in the catalogue"),
    (dict(record={"title": "Uyyala Loogavayya"}), "already in the catalogue"),
    (dict(record={"moods": []}), "at least one mood"),
    (dict(mood_evidence=[{**QUOTE, "needs_curator_confirmation": False}]), "needs_curator_confirmation"),
    (dict(mood_evidence=[{**QUOTE, "source": "https://example.com"}]), "trusted page"),
    (dict(record={"raaga": "Thodi", "moods": ["light_playful"]}, mood_evidence=[{**QUOTE, "mood": "light_playful"}]), "never be suggested"),
])
def test_check_refuses(cat, bad, expect):
    (r,) = run_check(cat, [cand(**bad)], {"items": []}, {"decisions": {}})
    assert not r["ok"] and any(expect in p for p in r["problems"]), r["problems"]


def test_never_resuggests_pending_or_rejected(cat):
    pending = {**cand(), "id": "u:1", "status": "pending"}
    (r,) = run_check(cat, [cand()], {"items": [pending]}, {"decisions": {}})
    assert "already waiting for review" in r["problems"]
    (r,) = run_check(cat, [cand()], {"items": [pending]}, {"decisions": {"u:1": {"status": "rejected"}}})
    assert any("rejected" in p for p in r["problems"])
    # The same song twice in one run: only the first passes.
    a, b = run_check(cat, [cand(), cand()], {"items": []}, {"decisions": {}})
    assert a["ok"] and not b["ok"]


def test_language_may_be_left_for_the_curator(cat):
    (r,) = run_check(cat, [cand(record={"language": ""})], {"items": []}, {"decisions": {}})
    assert r["ok"] and any("language" in w for w in r["warnings"])


def test_add_respects_limit_and_marks_the_agent(cat):
    cands = [cand(record={"title": f"Zz Song {c}"}) for c in "ABCD"]
    box, rep = run_add(cat, cands, {"items": []}, {"decisions": {}}, "U", limit=2)
    assert [r["ok"] for r in rep] == [True, True, False, False]
    assert len(box["items"]) == 2 and all(x["by"] == AGENT and x["status"] == "pending" for x in box["items"])
    assert all(x["id"].startswith("U:" + AGENT) for x in box["items"])


def test_add_stops_while_the_owner_has_enough_waiting(cat):
    box, _ = run_add(cat, [cand(record={"title": f"Zz Song {c}"}) for c in "AB"], {"items": []}, {"decisions": {}}, "U", limit=2)
    more = [cand(record={"title": f"Zz Song {c}"}) for c in "CD"]
    # Both earlier suggestions still wait: no room.
    full, rep = run_add(cat, more, box, {"decisions": {}}, "U", limit=2)
    assert [r["ok"] for r in rep] == [False, False] and "no room" in rep[0]["problems"][0]
    assert len(full["items"]) == 2
    # The owner decided one: room for one more. Suggestions from people don't count.
    people = {"items": box["items"] + [{"id": "V:1", "user": "V", "status": "pending", "name": "x"}]}
    dec = {"decisions": {box["items"][0]["id"]: {"status": "accepted", "at": "2026-11-21T00:00:00Z"}}}
    _, rep = run_add(cat, more, people, dec, "U", limit=2)
    assert [r["ok"] for r in rep] == [True, False]


def test_find_twin_matches_the_page(cat):
    """The curator decides 'already waiting' with the same rule as the page's findPendingTwin."""
    items = [{**cand(record={"title": "Zz Varnam", "raaga": "Vasantha"}), "id": "a", "status": "pending"},
             {**cand(record={"title": "Zzvarnam", "raaga": "Mohanam"}), "id": "b", "status": "pending"}]
    probes = [cand(record={"title": "Zz Varnam (Mohanam)", "raaga": ""}), cand(record={"title": "Zz Varnam", "raaga": "Vasantha"}),
              cand(record={"title": "Zz Varnam", "raaga": ""}), cand(record={"title": "Other"})]
    py = [(find_twin(cat, items, p) or {}).get("id") for p in probes]
    html = build(write=False)
    js_code = r'''
const vm = require("vm"); const fs = require("fs");
const {html, items, probes} = JSON.parse(fs.readFileSync(0, "utf8"));
const catLine = html.match(/^const CAT = .*;$/m)[0];
const core = html.slice(html.indexOf("/*@core-begin"), html.indexOf("/*@core-end*/"));
const code = "const $ = () => null; function renderTaste() {} function refreshCards() {} const use = () => Promise.resolve(null);\n"
  + catLine + "\n" + core + "\nRESULT = JSON.stringify(PROBES.map(p => (findPendingTwin(ITEMS, p) || {}).id || null));";
const sb = {ITEMS: items, PROBES: probes, RESULT: null, Blob, URL, console}; vm.runInNewContext(code, sb); process.stdout.write(sb.RESULT);'''
    out = subprocess.run(["node", "-e", js_code], input=json.dumps({"html": html, "items": items, "probes": probes}),
                         capture_output=True, text=True, check=True)
    assert py == json.loads(out.stdout) == ["b", "a", None, None]


def raaga_cand(**over):
    rec = {"name": "Zzraga", "type": "janya", "parent": "Shankarabharanam", "arohana": "S R2 G3 P D2 S",
           "avarohana": "S D2 P G3 R2 S", "moods": ["light_playful"]}
    rec.update(over.pop("record", {}))
    c = {"type": "addition", "kind": "raaga", "name": rec["name"], "record": rec, "sources": [SRC],
         "evidence": "Zzraga: 29 dheera shankaraabharaNam janya Aa: S R2 G3 P D2 S",
         "mood_evidence": [{"mood": "light_playful", "source": SRC, "quote": "a light, sprightly raaga for lilting songs",
                            "about": "raaga", "needs_curator_confirmation": True}],
         "details": "Grow the catalogue: a well-known raaga that's missing."}
    c.update(over)
    return c


def test_new_raaga_and_its_song_in_one_run(cat):
    song = cand(record={"title": "Zz Song In New Raaga", "raaga": "Zzraga", "moods": ["light_playful"]},
                mood_evidence=[{**QUOTE, "mood": "light_playful"}])
    # Song listed first: the raaga is still checked (and added) before it.
    rep = run_check(cat, [song, raaga_cand()], {"items": []}, {"decisions": {}})
    assert [r["ok"] for r in rep] == [True, True], rep
    assert "waiting for review" in rep[1]["warnings"][-1]
    box, _ = run_add(cat, [song, raaga_cand()], {"items": []}, {"decisions": {}}, "U", limit=10)
    assert [x["kind"] for x in box["items"]] == ["raaga", "krithi"]


def test_song_in_unknown_raaga_still_refused(cat):
    rep = run_check(cat, [cand(record={"title": "Zz Orphan", "raaga": "Zzraga"})], {"items": []}, {"decisions": {}})
    assert not rep[0]["ok"] and "suggest the raaga too" in rep[0]["problems"][0]


def test_rejected_raaga_does_not_count(cat):
    box, _ = run_add(cat, [raaga_cand()], {"items": []}, {"decisions": {}}, "U", limit=10)
    dec = {"decisions": {box["items"][0]["id"]: {"status": "rejected"}}}
    rep = run_check(cat, [cand(record={"title": "Zz Orphan", "raaga": "Zzraga"})], box, dec)
    assert not rep[0]["ok"]


def test_plan_splits_the_room_and_never_exceeds_it():
    from carnatic.gaps import plan
    assert plan(10) == {"gaps": 4, "new_krithis": 4, "new_raagas": 2}
    for room in range(0, 11):
        assert sum(plan(room).values()) == room


def test_wikipedia_is_a_trusted_source(cat):
    from carnatic.proposals import trusted
    assert trusted("https://en.wikipedia.org/wiki/Mohanam") and not trusted("http://en.wikipedia.org/wiki/Mohanam")
    assert not trusted("https://wikipedia.org.evil.com/x")
    c = cand(sources=["https://en.wikipedia.org/wiki/Neelambari"],
             mood_evidence=[{**QUOTE, "source": "https://en.wikipedia.org/wiki/Neelambari"}])
    assert run_check(cat, [c], {"items": []}, {"decisions": {}})[0]["ok"]
