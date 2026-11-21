"""Curator tools: edit a pending proposal, and import the chat page's suggestion-box export into the same queue."""
import json
import shutil

import pytest

from carnatic.catalog import DATA_DIR, Catalog
from carnatic.page_import import FORMAT, import_export
from carnatic.proposals import ProposalStore
from carnatic.review import describe, edit_command

SRC = "https://www.karnatik.com/c1256.shtml"
EV = "Karnatik.com: raagam aabhEri, taaLam aadi, Composer Mysore VaasudEvaacaarya"
MEANING = {"mood": "devotional_reflective", "source": "https://www.shivkumar.org/music/bhajare-re-manasa.htm",
           "quote": "Worship, O mind, Sri Raghuvira, who grants worldly joy and liberation", "about": "song",
           "user_confirmed": True}
REC = {"title": "Bhajare Re Manasa", "raaga": "Abheri", "composer": "Mysore Vasudevachar", "language": "Sanskrit",
       "tala": "Rupakam", "moods": ["devotional_reflective"]}


@pytest.fixture
def store(tmp_path):
    shutil.copytree(DATA_DIR, tmp_path / "data")
    return ProposalStore(tmp_path / "p.db", tmp_path / "data")


def krithi(store, title):
    return next((k for k in Catalog.load(store.data_dir).krithis if k.title == title), None)


def test_edit_then_approve(store):
    pid = store.propose_addition("u", Catalog.load(store.data_dir), "krithi", dict(REC), [SRC], EV, [MEANING])["proposal_id"]
    res = edit_command(store, f'{pid} tala=Adi moods="devotional_reflective;calm_anxious" note="tala per Karnatik.com"')
    assert res["ok"], res
    shown = describe(store.get(pid))
    assert "edited:" in shown and "calm_anxious" in shown and "tala per Karnatik.com" in shown
    assert store.approve(pid)["status"] == "approved"
    k = krithi(store, "Bhajare Re Manasa")
    assert k.tala == "Adi" and k.moods == ["devotional_reflective", "calm_anxious"]
    assert "calm_anxious (curator)" in k.notes and "Curator edited: moods, tala" in k.notes
    assert "devotional_reflective (inferred from" in k.notes          # the confirmed inference keeps its basis


def test_edit_rejects_bad_input(store):
    pid = store.propose_addition("u", Catalog.load(store.data_dir), "krithi", dict(REC), [SRC], EV, [MEANING])["proposal_id"]
    assert "unknown mood" in edit_command(store, f"{pid} moods=hungry")["error"]
    assert "unknown fields" in edit_command(store, f"{pid} colour=blue")["error"]
    assert "not in the catalogue" in edit_command(store, f"{pid} raaga=Zorbulu")["error"]
    assert "error" in edit_command(store, "tala=Adi")
    store.reject(pid)
    assert "not pending" in edit_command(store, f"{pid} tala=Adi")["error"]


def test_edit_mood_correction(store):
    cat = Catalog.load(store.data_dir)
    pid = store.propose_correction("u", cat, "krithi", "Jagadoddharana", "moods",
                                   {"remove": ["light_playful"], "add": []}, "soothing, not playful")["proposal_id"]
    assert edit_command(store, f"{pid} add=calm_anxious")["ok"]
    assert store.get(pid)["payload"]["suggested"] == {"remove": ["light_playful"], "add": ["calm_anxious"]}


def export(*items):
    return {"format": FORMAT, "exported_at": "2026-11-21T12:00:00Z", "items": list(items)}


def test_import_page_export(store):
    accepted = {"id": "u1:1", "user": "u1", "type": "addition", "kind": "krithi", "status": "accepted",
                "record": dict(REC, tala="Adi"), "sources": [SRC], "evidence": EV, "mood_evidence": [MEANING],
                "curator_note": "checked"}
    pending = {"id": "u1:2", "user": "u1", "type": "correction", "status": "pending", "item_type": "krithi",
               "item_name": "Jagadoddharana", "remove_moods": ["light_playful"], "reason": "soothing"}
    rejected = {"id": "u1:3", "user": "u1", "type": "addition", "kind": "krithi", "status": "rejected",
                "record": {"title": "Nope"}}
    incomplete = {"id": "u1:4", "user": "u1", "type": "addition", "kind": "krithi", "status": "pending",
                  "record": {"title": "Only A Title"}, "sources": [SRC], "evidence": EV}
    rep = {r["page_id"]: r["result"] for r in import_export(store, export(accepted, pending, rejected, incomplete))}
    assert rep["u1:1"].startswith("approved")
    assert rep["u1:2"] == "queued for review"
    assert rep["u1:3"].startswith("skipped: rejected")
    assert rep["u1:4"].startswith("not imported: missing")
    assert krithi(store, "Bhajare Re Manasa").tala == "Adi"
    queued = store.list("pending")
    assert len(queued) == 1 and "from the chat page" in describe(queued[0])
    # Re-importing the same file changes nothing.
    again = import_export(store, export(accepted, pending))
    assert all(r["result"] == "skipped: already imported" for r in again)
    assert len(store.list(None)) == 2


def test_import_refuses_unverified_moods(store):
    bad = {"id": "u1:9", "user": "u1", "type": "addition", "kind": "krithi", "status": "accepted",
           "record": dict(REC), "sources": [SRC], "evidence": EV,
           "mood_evidence": [{**MEANING, "user_confirmed": False}]}
    (r,) = import_export(store, export(bad))
    assert r["result"].startswith("not imported") and krithi(store, "Bhajare Re Manasa") is None


def test_import_rejects_other_files(store):
    assert "error" in import_export(store, {"items": []})[0]
    json.dumps(export())  # the format is plain JSON


SRC_V = "https://www.shivkumar.org/music/varnams/Ninnukori-Vasantha-Varnam.htm"
SRC_M = "https://www.shivkumar.org/music/varnams/ninnukori.htm"


def test_updates_merge_into_the_pending_addition(store):
    """Regression: each update to a suggested song (mood, then language) became a new proposal, and the last one
    had lost raaga/composer/tala. Two songs with the same title in different raagas must stay separate."""
    cat = Catalog.load(store.data_dir)
    v = {"title": "Zz Test Varnam", "raaga": "Vasantha", "composer": "Tacchur Singaraachari", "language": "Telugu",
         "tala": "Adi", "form": "varnam"}
    m = {"title": "Zztestvarnam", "raaga": "Mohanam", "composer": "Ramnad Sreenivasa Iyengar", "language": "Telugu",
         "tala": "Adi", "form": "varnam"}
    ev = "Ninnu kori yunnara Ragam : Vasantha Talam : Adi Composer : Tacchur Singaaraachari"
    a = store.propose_addition("u", cat, "krithi", v, [SRC_V], ev)
    b = store.propose_addition("u", cat, "krithi", m, [SRC_M], "Ninnukori Ragam : Mohanam Talam : Adi Composer : Ramnad")
    assert a["proposal_id"] != b["proposal_id"]                        # same title, different raagas
    mood = {"mood": "romantic_nostalgic", "source": SRC_V, "quote": "I am longing for you. I beseech you to uphold your affection.",
            "about": "song", "user_confirmed": True}
    # The update carries only the title (with the raaga in brackets) and the mood: it must not erase anything.
    u = store.propose_addition("u", cat, "krithi", {"title": "Zz Test Varnam (Vasantha)", "moods": ["romantic_nostalgic"]},
                               [SRC_V], ev, [mood])
    assert u["updated"] and u["proposal_id"] == a["proposal_id"]
    assert len(store.list("pending")) == 2
    rec = store.get(a["proposal_id"])["payload"]["record"]
    assert rec == {**v, "moods": ["romantic_nostalgic"]}               # clean title kept, nothing lost
    assert store.get(a["proposal_id"])["payload"]["updates"]
    # Once decided, a later suggestion of the same song is a new proposal (the catalogue check then applies).
    store.reject(a["proposal_id"])
    again = store.propose_addition("u", cat, "krithi", v, [SRC_V], ev)
    assert again["proposal_id"] not in (a["proposal_id"], b["proposal_id"]) and not again.get("updated")


def test_updates_merge_into_the_pending_correction(store):
    cat = Catalog.load(store.data_dir)
    one = store.propose_correction("u", cat, "krithi", "Jagadoddharana", "moods", {"remove": ["light_playful"], "add": []}, "not upbeat")
    two = store.propose_correction("u", cat, "krithi", "Jagadoddharana", "moods", {"remove": [], "add": ["calm_anxious"]}, "it's calming")
    assert two["updated"] and two["proposal_id"] == one["proposal_id"] and len(store.list("pending")) == 1
    pay = store.get(one["proposal_id"])["payload"]
    assert pay["suggested"] == {"remove": ["light_playful"], "add": ["calm_anxious"]}
    assert "not upbeat" in pay["reason"] and "calming" in pay["reason"]


def test_reimport_of_an_updated_page_suggestion_updates_the_queue(store):
    item = {"id": "p:9", "user": "u", "type": "addition", "kind": "krithi", "status": "pending", "updated_at": "",
            "record": {"title": "Zz Test Varnam", "raaga": "Vasantha", "composer": "Tacchur Singaraachari", "language": "Telugu", "tala": "Adi"},
            "sources": [SRC_V], "evidence": "Ninnu kori yunnara Ragam : Vasantha Talam : Adi Composer : Tacchur"}
    assert import_export(store, export(item))[0]["result"] == "queued for review"
    assert import_export(store, export(item))[0]["result"] == "skipped: already imported"
    later = {**item, "updated_at": "2026-11-21T12:20:00Z", "record": {**item["record"], "form": "varnam"}}
    assert import_export(store, export(later))[0]["result"] == "updated the queued proposal"
    (p,) = store.list("pending")
    assert p["payload"]["record"]["form"] == "varnam"


def test_chat_agent_cannot_defer_mood_confirmation(tmp_path):
    """Only the background curator's suggestions may leave a mood for the curator to confirm; the chat agent may not."""
    from carnatic.profile import ProfileStore
    from carnatic.tools import Toolbox
    shutil.copytree(DATA_DIR, tmp_path / "data")
    tb = Toolbox(Catalog.load(tmp_path / "data"), ProfileStore(tmp_path / "u.db"), "u", ProposalStore(tmp_path / "p.db", tmp_path / "data"))
    res = tb.run("propose_addition", {"kind": "krithi", "record": {**REC, "title": "Zz Unconfirmed"}, "sources": [SRC], "evidence": EV,
                                      "mood_evidence": [{**MEANING, "user_confirmed": False, "needs_curator_confirmation": True}]})
    assert "user_confirmed" in res["error"]
