"""Bring the chat page's suggestion box into the curator queue, so there is one queue to review.

The page's owner-only Review panel exports a JSON file ("Export for the repo"). Import it with
    python -m carnatic.review import manoraga-suggestions.json
Each entry becomes a normal proposal (same validation as the agent's own). Entries you accepted in the page, or
already added to the page's catalogue ("applied"), are approved straight away (catalogue written, validated, rolled back on error); rejected ones are skipped; the rest
wait in the queue. Re-importing the same file is safe: entries already imported are skipped.
"""
from __future__ import annotations

import json

from .catalog import Catalog
from .proposals import ProposalStore

FORMAT = "manoraga-suggestions/1"


def _imported(store: ProposalStore) -> dict[str, dict]:
    """page id -> the proposal it became (the latest, if several)."""
    out = {}
    for p in store.list(None):
        o = p["payload"].get("origin")
        if isinstance(o, dict) and o.get("page_id"):
            out[o["page_id"]] = p
    return out


def import_export(store: ProposalStore, data: dict) -> list[dict]:
    if data.get("format") != FORMAT:
        return [{"error": f"not a ManoRaga suggestions export (expected format {FORMAT})"}]
    seen = _imported(store)
    report = []
    for it in data.get("items", []):
        pid_page = str(it.get("id", ""))
        label = it.get("record", {}).get("title") or it.get("record", {}).get("name") or it.get("item_name") or it.get("name") or "?"
        row = {"page_id": pid_page, "item": label, "page_status": it.get("status", "pending")}
        if not pid_page:
            report.append({**row, "result": "skipped: no id"}); continue
        if pid_page in seen and (seen[pid_page]["status"] != "pending" or it.get("updated_at", "") <= seen[pid_page]["payload"]["origin"].get("page_updated_at", "")):
            report.append({**row, "result": "skipped: already imported"}); continue
        if it.get("status") == "rejected":
            report.append({**row, "result": "skipped: rejected in the page"}); continue
        origin = {"page_id": pid_page, "from": "chat page", "page_status": it.get("status", "pending"),
                  "curator_note": it.get("curator_note", ""), "page_updated_at": it.get("updated_at", "")}
        cat = Catalog.load(store.data_dir)
        user = "page:" + str(it.get("user", "?"))
        if it.get("type") == "addition":
            mev = [dict(e) for e in it.get("mood_evidence") or []]
            res = store.propose_addition(user, cat, it.get("kind", "krithi"), dict(it.get("record") or {}),
                                         list(it.get("sources") or []), it.get("evidence", ""), mev, origin)
        elif it.get("type") == "correction":
            if it.get("remove_moods") or it.get("add_moods"):
                res = store.propose_correction(user, cat, it.get("item_type", "krithi"), it.get("item_name", ""), "moods",
                                               {"remove": it.get("remove_moods") or [], "add": it.get("add_moods") or []},
                                               it.get("reason", ""), it.get("sources") or [], origin)
            else:
                res = store.propose_correction(user, cat, it.get("item_type", "krithi"), it.get("item_name", ""),
                                               it.get("field", ""), it.get("suggested_value", ""), it.get("reason", ""),
                                               it.get("sources") or [], origin)
        else:
            res = {"error": f"unknown entry type {it.get('type')!r}"}
        if "error" in res:
            if it.get("status") == "applied" and "already in the catalogue" in res["error"]:
                report.append({**row, "result": "skipped: already in the catalogue"}); continue
            report.append({**row, "result": "not imported: " + res["error"]}); continue
        pid = res["proposal_id"]
        if it.get("status") in ("accepted", "applied"):
            ap = store.approve(pid, ("added to the page's catalogue" if it.get("status") == "applied" else "accepted in the chat page") + (f": {it.get('curator_note')}" if it.get("curator_note") else ""))
            report.append({**row, "proposal_id": pid,
                           "result": "approved, catalogue updated" if ap.get("ok") else "queued; approval failed: " + ap["error"]})
        else:
            report.append({**row, "proposal_id": pid, "result": "updated the queued proposal" if res.get("updated") else "queued for review"})
    return report


def import_file(store: ProposalStore, path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return import_export(store, json.load(f))
