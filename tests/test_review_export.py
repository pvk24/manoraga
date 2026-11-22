"""Contract test: what the page's Review panel exports is exactly what carnatic/page_import.py imports."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from build_web import build  # noqa: E402
from carnatic.catalog import DATA_DIR, Catalog  # noqa: E402
from carnatic.page_import import import_export  # noqa: E402
from carnatic.proposals import ProposalStore  # noqa: E402

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="Node.js not installed")
SRC = "https://www.karnatik.com/c1256.shtml"
MEANING = {"mood": "devotional_reflective", "source": "https://www.shivkumar.org/music/bhajare-re-manasa.htm",
           "quote": "Worship, O mind, Sri Raghuvira, who grants worldly joy and liberation", "about": "song",
           "user_confirmed": True}
ITEMS = [
    # New-format addition, accepted after the curator fixed the tala and added a mood.
    {"id": "u1:a", "user": "u1", "ts": "2026-11-21T10:00:00Z", "type": "addition", "kind": "krithi", "name": "Zz Bhajare Test",
     "record": {"title": "Zz Bhajare Test", "raaga": "Abheri", "composer": "Mysore Vasudevachar", "language": "Sanskrit",
                "tala": "Rupakam", "moods": ["devotional_reflective"]},
     "sources": [SRC], "evidence": "Karnatik.com: raagam aabhEri, taaLam aadi, Mysore VaasudEvaacaarya",
     "moods": ["devotional_reflective"], "mood_evidence": [MEANING]},
    # A mood correction, left undecided.
    {"id": "u1:b", "user": "u1", "ts": "2026-11-21T10:01:00Z", "type": "correction", "item_type": "krithi",
     "item_name": "Jagadoddharana", "remove_moods": ["light_playful"], "reason": "it's soothing, not playful"},
    # Old-format entry (before ids and records), rejected.
    {"kind": "krithi", "name": "Some Song", "details": "user asked", "ts": "2026-11-20T09:00:00Z"},
]
DECISIONS = {"u1:a": {"status": "accepted", "note": "tala per Karnatik.com",
                      "edits": {"record": {"tala": "Adi"}, "moods": ["devotional_reflective", "calm_anxious"]}},
             "u:2026-11-20T09:00:00Z": {"status": "rejected"}}


def page_export():
    html = build(write=False)
    out = subprocess.run(["node", str(ROOT / "tests" / "js_review_runner.js")], input=json.dumps(
        {"html": html, "items": ITEMS, "decisions": DECISIONS}), capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def test_page_export_imports_cleanly(tmp_path):
    exp = page_export()
    ids = [i["id"] for i in exp["items"]]
    assert ids == ["u1:a", "u1:b"]                                   # rejected one isn't exported
    a = exp["items"][0]
    assert a["record"]["tala"] == "Adi" and a["record"]["moods"] == ["devotional_reflective", "calm_anxious"]
    assert {e["mood"]: e["source"] for e in a["mood_evidence"]}["calm_anxious"] == "curator"
    shutil.copytree(DATA_DIR, tmp_path / "data")
    store = ProposalStore(tmp_path / "p.db", tmp_path / "data")
    rep = {r["page_id"]: r["result"] for r in import_export(store, exp)}
    assert rep == {"u1:a": "approved, catalogue updated", "u1:b": "queued for review"}
    k = next(k for k in Catalog.load(tmp_path / "data").krithis if k.title == "Zz Bhajare Test")
    assert k.tala == "Adi" and k.moods == ["devotional_reflective", "calm_anxious"] and "calm_anxious (curator)" in k.notes


APPLY = [
    {"id": "p:1", "type": "addition", "kind": "krithi", "status": "applied",
     "record": {"title": "Zz Bhajare Test", "raaga": "abheri", "composer": "Mysore Vasudevachar", "language": "Sanskrit",
                "tala": "Adi", "moods": ["devotional_reflective", "calm_anxious"]},
     "sources": [SRC], "evidence": "Karnatik.com: raagam aabhEri, taaLam aadi, Mysore VaasudEvaacaarya",
     "mood_evidence": [MEANING, {"mood": "calm_anxious", "source": "curator", "quote": "set by the curator"}]},
    {"id": "p:2", "type": "correction", "status": "applied", "item_type": "krithi", "item_name": "Jagadoddharana",
     "remove_moods": ["romantic_nostalgic"], "add_moods": ["calm_anxious"], "reason": "soothing", "sources": []},
    {"id": "p:3", "type": "correction", "status": "applied", "item_type": "krithi", "item_name": "Emi Jesite",
     "field": "tala", "suggested_value": "Adi", "reason": "test", "sources": [SRC]},
    # Must be refused by both: unconfirmed inferred mood; raaga not in catalogue; mood the raaga avoids.
    {"id": "p:4", "type": "addition", "kind": "krithi", "status": "applied",
     "record": {"title": "X1", "raaga": "Abheri", "composer": "c", "language": "Tamil", "moods": ["devotional_reflective"]},
     "sources": [SRC], "evidence": "x" * 25, "mood_evidence": [{**MEANING, "user_confirmed": False}]},
    {"id": "p:5", "type": "addition", "kind": "krithi", "status": "applied",
     "record": {"title": "X2", "raaga": "Zorbulu", "composer": "c", "language": "Tamil"}, "sources": [SRC], "evidence": "x" * 25},
    {"id": "p:6", "type": "addition", "kind": "krithi", "status": "applied",
     "record": {"title": "X3", "raaga": "Thodi", "composer": "c", "language": "Tamil", "moods": ["light_playful"]},
     "sources": [SRC], "evidence": "x" * 25, "mood_evidence": [{"mood": "light_playful", "source": "user", "quote": "fun"}]},
]


def test_page_catalogue_changes_match_python_approval(tmp_path):
    """'Add to catalogue' in the page must give the same catalogue as approving the same entries in the repo."""
    html = build(write=False)
    out = json.loads(subprocess.run(["node", str(ROOT / "tests" / "js_apply_runner.js")], input=json.dumps(
        {"html": html, "items": APPLY}), capture_output=True, text=True, check=True).stdout)
    page_ok = [r["error"] is None for r in out["results"]]
    shutil.copytree(DATA_DIR, tmp_path / "data")
    store = ProposalStore(tmp_path / "p.db", tmp_path / "data")
    rep = import_export(store, {"format": "manoraga-suggestions/1", "items": APPLY})
    py_ok = [r["result"].startswith("approved") for r in rep]
    assert page_ok == py_ok == [True, True, True, False, False, False], (out["results"], rep)
    cat = Catalog.load(tmp_path / "data")
    fields = ("title", "raaga", "composer", "language", "tala", "form", "moods", "avoid_moods", "sources", "verified")
    for title in ("Zz Bhajare Test", "Jagadoddharana", "Emi Jesite"):
        py = next(k for k in cat.krithis if k.title == title)
        js = next(k for k in out["krithis"] if k["title"] == title)
        assert {f: getattr(py, f) for f in fields} == {f: js[f] for f in fields}, title
        assert py.verified is True, f"{title}: the owner accepted it, so it is verified"


V = "https://www.shivkumar.org/music/varnams/Ninnukori-Vasantha-Varnam.htm"
M = "https://www.shivkumar.org/music/varnams/ninnukori.htm"
# What the page actually sent on 21 Nov: each varnam three times (facts; + mood; + "both are in Telugu"),
# the last time with only title "(Raaga)" + mood. Two different songs share the title.
SENDS = [
    {"type": "addition", "kind": "krithi", "name": "Ninnu Kori (Vasantha)", "sources": [V], "evidence": "Ninnu kori yunnara Ragam : Vasantha Talam : Adi",
     "record": {"title": "Ninnu Kori", "raaga": "Vasantha", "composer": "Tacchur Singaaraachari", "tala": "Adi", "form": "Varnam"}},
    {"type": "addition", "kind": "krithi", "name": "Ninnukori (Mohanam)", "sources": [M], "evidence": "Ninnukori Ragam : Mohanam Talam : Adi",
     "record": {"title": "Ninnukori", "raaga": "Mohanam", "composer": "Ramnad Sreenivasa Iyengar", "tala": "Adi", "form": "Varnam"}},
    {"type": "addition", "kind": "krithi", "name": "Ninnu Kori (Vasantha)", "sources": [V], "evidence": "I am longing for you.",
     "record": {"title": "Ninnu Kori", "raaga": "Vasantha", "composer": "Tacchur Singaaraachari", "tala": "Adi", "form": "Varnam", "moods": ["romantic_nostalgic"]},
     "mood_evidence": [{"mood": "romantic_nostalgic", "source": V, "quote": "I am longing for you. I beseech you to uphold your affection for me.", "about": "song", "user_confirmed": True}]},
    {"type": "addition", "kind": "krithi", "name": "Ninnukori (Mohanam)", "sources": [M], "evidence": "O Srinivasa! I pray to your existence.",
     "record": {"title": "Ninnukori", "raaga": "Mohanam", "moods": ["devotional_reflective"]},
     "mood_evidence": [{"mood": "devotional_reflective", "source": M, "quote": "O Srinivasa! I pray to your existence. Kindly show mercy upon me.", "about": "song", "user_confirmed": True}]},
    {"type": "addition", "kind": "krithi", "name": "Ninnu Kori (Vasantha)", "sources": [V], "evidence": "User: both are in telugu",
     "record": {"title": "Ninnu Kori (Vasantha)", "language": "Telugu", "moods": ["romantic_nostalgic"]}},
    {"type": "addition", "kind": "krithi", "name": "Ninnukori (Mohanam)", "sources": [M], "evidence": "User: both are in telugu",
     "record": {"title": "Ninnukori (Mohanam)", "language": "Telugu", "moods": ["devotional_reflective"]}},
]


def test_updates_merge_in_the_page_box_like_in_python():
    from carnatic.proposals import merge_addition
    html = build(write=False)
    box = json.loads(subprocess.run(["node", str(ROOT / "tests" / "js_box_runner.js")], input=json.dumps(
        {"html": html, "sends": SENDS}), capture_output=True, text=True, check=True).stdout)
    assert len(box) == 2
    v, m = box
    assert v["record"] == {"title": "Ninnu Kori", "raaga": "Vasantha", "composer": "Tacchur Singaaraachari", "tala": "Adi",
                           "form": "Varnam", "moods": ["romantic_nostalgic"], "language": "Telugu"}
    assert m["record"]["raaga"] == "Mohanam" and m["record"]["language"] == "Telugu" and m["record"]["composer"]
    assert v["updates"] == 2 and m["updates"] == 2 and v["mood_evidence"] and m["mood_evidence"]
    # Python's merge gives the same record for the same sequence.
    py = {"record": {}, "sources": [], "evidence": ""}
    for e in SENDS[0::2]:
        py = merge_addition(py, e)
    assert py["record"] == v["record"] and py["mood_evidence"] == v["mood_evidence"] and py["sources"] == v["sources"]


def test_curator_agent_finds_are_confirmed_by_accepting():
    """A background-curator suggestion: its inferred mood is unconfirmed until the owner accepts it in the page."""
    bot = {"id": "U:curator-agent-x", "user": "U", "ts": "2026-11-22T03:00:00Z", "status": "pending", "by": "curator-agent",
           "type": "addition", "kind": "krithi", "name": "Zz Lullaby",
           "record": {"title": "Zz Lullaby", "raaga": "Neelambari", "composer": "Test", "language": "Tamil", "tala": "Adi",
                      "form": "krithi", "moods": ["wind_down_sleep"]},
           "sources": [SRC], "evidence": "raagam neelaambari taaLam aadi Composer Test",
           "mood_evidence": [{"mood": "wind_down_sleep", "source": SRC, "quote": "a lullaby rocking the child to sleep gently",
                              "about": "song", "needs_curator_confirmation": True}]}
    html = build(write=False)

    def export(decisions):
        out = subprocess.run(["node", str(ROOT / "tests" / "js_review_runner.js")], input=json.dumps(
            {"html": html, "items": [bot], "decisions": decisions}), capture_output=True, text=True, check=True)
        return json.loads(out.stdout)

    def page_check(item):
        out = subprocess.run(["node", str(ROOT / "tests" / "js_apply_runner.js")], input=json.dumps(
            {"html": html, "items": [item]}), capture_output=True, text=True, check=True)
        return json.loads(out.stdout)["results"][0]["error"]

    pending = export({})["items"][0]
    assert pending["mood_evidence"][0].get("user_confirmed") is not True
    assert page_check(pending)                                   # can't be added before the owner accepts
    accepted = export({bot["id"]: {"status": "accepted", "at": "2026-11-22T04:00:00Z"}})["items"][0]
    assert accepted["mood_evidence"][0]["user_confirmed"] is True and accepted["mood_evidence"][0]["confirmed_by"] == "curator"
    assert page_check(accepted) is None                          # Add to catalogue works once accepted

    import tempfile
    d = Path(tempfile.mkdtemp())
    shutil.copytree(DATA_DIR, d / "data")
    store = ProposalStore(d / "p.db", d / "data")
    assert import_export(store, {"format": "manoraga-suggestions/1", "items": [pending]})[0]["result"] == "queued for review"
    d2 = Path(tempfile.mkdtemp())
    shutil.copytree(DATA_DIR, d2 / "data")
    store2 = ProposalStore(d2 / "p.db", d2 / "data")
    assert import_export(store2, {"format": "manoraga-suggestions/1", "items": [accepted]})[0]["result"].startswith("approved")
    k = next(k for k in Catalog.load(d2 / "data").krithis if k.title == "Zz Lullaby")
    assert "found by the curator agent, confirmed by the curator" in k.notes and k.moods == ["wind_down_sleep"]


def test_only_the_owners_accept_marks_a_row_verified(tmp_path):
    """Owner's rule (21 Nov 2026): Accept in the Review panel marks a new row verified; any other approval doesn't."""
    shutil.copytree(DATA_DIR, tmp_path / "data")
    store = ProposalStore(tmp_path / "p.db", tmp_path / "data")
    src = "https://www.karnatik.com/c9999.shtml"
    for title, verified in (("Zz Plain Approve", False), ("Zz Owner Accept", True)):
        r = store.propose_addition("u", Catalog.load(tmp_path / "data"), "krithi",
                                   {"title": title, "raaga": "Mohanam", "composer": "X", "language": "Tamil"}, [src],
                                   "raagam: mOhanam Composer: X Language: Tamil")
        assert store.approve(r["proposal_id"], verified=verified)["ok"]
    got = {k.title: k.verified for k in Catalog.load(tmp_path / "data").krithis if k.title.startswith("Zz")}
    assert got == {"Zz Plain Approve": False, "Zz Owner Accept": True}


NEW_MOOD = {"key": "festive_wedding", "label": "Festive / wedding", "when_to_use": "Weddings, festivals, family celebrations",
            "fallback": ["joyful_celebrate", "grand_uplifted"]}


def test_owner_can_create_a_mood_while_reviewing(tmp_path):
    """Owner's rule (22 Nov 2026): in the Review panel the owner can add a brand-new mood to a suggested song.
    The page's export carries it, and the page's Add to catalogue and the repo import give the same result."""
    item = {"id": "u1:nm", "user": "u1", "ts": "2026-11-22T10:00:00Z", "type": "addition", "kind": "krithi",
            "name": "Zz Wedding Test", "record": {"title": "Zz Wedding Test", "raaga": "Mohanam", "composer": "X",
                                                   "language": "Tamil", "tala": "Adi"},
            "sources": [SRC], "evidence": "raagam: mOhanam taaLam: aadi Composer: X Language: Tamil"}
    dec = {"u1:nm": {"status": "applied", "at": "2026-11-22T10:01:00Z",
                     "edits": {"moods": ["festive_wedding"], "new_moods": [NEW_MOOD], "record": {}}}}
    html = build(write=False)
    exp = json.loads(subprocess.run(["node", str(ROOT / "tests" / "js_review_runner.js")], capture_output=True, text=True,
                                    input=json.dumps({"html": html, "items": [item], "decisions": dec}), check=True).stdout)
    entry = exp["items"][0]
    assert entry["new_moods"] == [NEW_MOOD] and entry["record"]["moods"] == ["festive_wedding"]
    bad = {**entry, "id": "u1:bad", "record": {**entry["record"], "title": "Zz Bad Mood"},
           "new_moods": [{**NEW_MOOD, "key": "festive_bad", "fallback": ["no_such_mood"]}],
           "mood_evidence": [{"mood": "festive_bad", "source": "curator", "quote": "set by the curator"}]}
    bad["record"]["moods"] = ["festive_bad"]
    page = json.loads(subprocess.run(["node", str(ROOT / "tests" / "js_apply_runner.js")], capture_output=True, text=True,
                                     input=json.dumps({"html": html, "items": [entry, bad]}), check=True).stdout)
    shutil.copytree(DATA_DIR, tmp_path / "data")
    store = ProposalStore(tmp_path / "p.db", tmp_path / "data")
    rep = import_export(store, {"format": "manoraga-suggestions/1", "items": [entry, bad]})
    assert [r["error"] is None for r in page["results"]] == [r["result"].startswith("approved") for r in rep] == [True, False]
    cat = Catalog.load(tmp_path / "data")
    mo = cat.moods["festive_wedding"]
    assert (mo.label, mo.when_to_use, mo.fallback) == (NEW_MOOD["label"], NEW_MOOD["when_to_use"], NEW_MOOD["fallback"])
    assert page["moods"]["festive_wedding"] == {"label": NEW_MOOD["label"], "when": NEW_MOOD["when_to_use"], "fallback": NEW_MOOD["fallback"]}
    py = next(k for k in cat.krithis if k.title == "Zz Wedding Test")
    js = next(k for k in page["krithis"] if k["title"] == "Zz Wedding Test")
    assert py.moods == js["moods"] == ["festive_wedding"] and py.verified is True
    # The new mood works for suggestions straight away.
    from carnatic.profile import ProfileStore
    from carnatic.tools import Toolbox
    recs = Toolbox(cat, ProfileStore(tmp_path / "u.db"), "u").run("recommend", {"moods": ["festive_wedding"]})["recommendations"]
    assert recs[0]["krithis"][0]["title"] == "Zz Wedding Test"
