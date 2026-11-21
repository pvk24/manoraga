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
