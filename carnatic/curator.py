"""Deterministic half of the background curator: check what the curator agent found, then add it to the
suggestion box the owner reviews in the chat page.

    python -m carnatic.curator check candidates.json [--box box.json] [--decisions decisions.json]
    python -m carnatic.curator add candidates.json --box box.json [--decisions decisions.json] --uid USER --out new_box.json
    python -m carnatic.curator room --box box.json [--decisions decisions.json]   # how many more fit

`candidates.json` is a list of suggestion-box entries (the page's format) that the agent researched on the trusted
sites: type "addition", kind "krithi" (or "raaga"), a full record, sources, quoted evidence, and moods inferred from
the song's meaning with `needs_curator_confirmation: true` (nobody confirmed them yet: the owner does that by
accepting in the Review panel). `box.json` is the suggestion-box document ({"items": [...]}) and `decisions.json` the
Review panel's decisions ({"decisions": {...}}), both read from the page's storage.

`check` prints, per candidate, whether it passes the catalogue's rules and why not. `add` merges the passing ones
into the box exactly as the page does (an update to a pending twin updates it; nothing is duplicated) and writes the
new box document to `--out`, ready to store. Rejected songs, songs already in the catalogue and songs already waiting
for review are never re-suggested.
"""
from __future__ import annotations

import json
import random
import re
import shutil
import string
import sys
import tempfile
import time
from pathlib import Path

from .catalog import DATA_DIR, RAGAMALIKA, Catalog, _norm, is_ragamalika
from .proposals import KRITHI_FIELDS, RAAGA_FIELDS, ProposalStore, _base_title, _filled, _paren, merge_addition, trusted

AGENT = "curator-agent"


def _raaga_of(cat: Catalog, e: dict) -> str:
    rec = e.get("record") or {}
    key = "name" if e.get("kind") == "raaga" else "title"
    cand = rec.get("raaga") or _paren(rec.get(key)) or _paren(e.get("name"))
    r = cat.resolve_raaga(cand) if cand else None
    return r.name if r else str(cand or "").strip().lower()


def _title_key(e: dict) -> str:
    key = "name" if e.get("kind") == "raaga" else "title"
    return _norm(_base_title((e.get("record") or {}).get(key) or e.get("name") or ""))


def find_twin(cat: Catalog, items: list[dict], e: dict, statuses=("pending",)) -> dict | None:
    """The box entry `e` would update (mirror of findPendingTwin in web/template.html)."""
    if e.get("type") != "addition":
        return None
    t = _title_key(e)
    if not t:
        return None
    c = [x for x in items if x.get("status", "pending") in statuses and x.get("type") == "addition"
         and (x.get("kind") == "raaga") == (e.get("kind") == "raaga") and _title_key(x) == t]
    if e.get("kind") != "raaga" and c:
        mine = _raaga_of(cat, e)
        exact = [x for x in c if mine and _raaga_of(cat, x) == mine]
        c = exact if exact else ([x for x in c if not _raaga_of(cat, x)] if mine else c)
    return c[0] if len(c) == 1 else None


def merge_into_box(cat: Catalog, items: list[dict], e: dict, ts: str, uid: str) -> tuple[dict, bool]:
    """Add `e` to the box like the page's sendToCurator: update a pending twin, else append. Returns (entry, updated)."""
    twin = find_twin(cat, items, e)
    if twin:
        m = merge_addition(twin, e)
        twin.update(record=m["record"], moods=list(m["record"].get("moods") or []), mood_evidence=m["mood_evidence"],
                    sources=m["sources"], evidence=m["evidence"], details=e.get("details") or twin.get("details", ""))
        twin["updated_at"] = ts
        twin["updates"] = (twin.get("updates") or 0) + 1
        return twin, True
    rid = "".join(random.choices(string.ascii_lowercase + string.digits, k=12))
    entry = {**e, "id": f"{uid}:{AGENT}-{rid}", "user": uid, "ts": ts, "status": "pending",
             "moods": list((e.get("record") or {}).get("moods") or [])}
    items.append(entry)
    return entry, False


def check_candidate(cat: Catalog, e: dict, items: list[dict], decisions: dict) -> dict:
    rec = dict(e.get("record") or {})
    kind = e.get("kind", "krithi")
    key = "name" if kind == "raaga" else "title"
    name = rec.get(key) or e.get("name") or "?"
    problems, warnings = [], []
    if e.get("type") != "addition" or kind not in ("krithi", "raaga"):
        return {"name": name, "ok": False, "problems": ["must be an addition of a krithi or raaga"], "warnings": []}
    allowed = KRITHI_FIELDS if kind == "krithi" else RAAGA_FIELDS
    extra = set(rec) - allowed
    if extra:
        problems.append(f"unknown fields {sorted(extra)}")
    need = ["title", "raaga", "composer", "tala", "form"] if kind == "krithi" else ["name", "type", "arohana", "avarohana"]
    missing = [f for f in need if not _filled(rec.get(f))]
    if missing:
        problems.append(f"missing {missing}: research them on the trusted sites")
    if kind == "krithi" and not _filled(rec.get("language")):
        warnings.append("language not stated on the trusted sources: the curator fills it in when reviewing")
    srcs = e.get("sources") or []
    if not srcs or not all(trusted(u) for u in srcs):
        problems.append("needs at least one source, all https pages on the trusted sites")
    if len(str(e.get("evidence") or "").strip()) < 20:
        problems.append("evidence must quote what the source page says")
    raaga, new_raaga = None, None
    if kind == "krithi" and _filled(rec.get("raaga")):
        raaga = cat.resolve_raaga(rec["raaga"])
        if raaga:
            rec["raaga"] = raaga.name
        elif is_ragamalika(rec["raaga"]):
            rec["raaga"] = RAGAMALIKA
            if not _filled(rec.get("notes")):
                problems.append("a ragamalika song needs its raagas in notes, from the trusted page")
        else:
            # A raaga suggested in this run (listed before its songs) or already waiting for review is fine:
            # the owner adds the raaga first, then its songs.
            new_raaga = _waiting_raaga(items, decisions, rec["raaga"])
            if not new_raaga:
                problems.append(f"raaga '{rec['raaga']}' is not in the catalogue: suggest the raaga too "
                                "(before its songs) or leave the song out")
            else:
                rec["raaga"] = new_raaga["name"]
                warnings.append(f"{new_raaga['name']} is a new raaga waiting for review: the owner adds it first")
    # Never re-suggest: in the catalogue, waiting for review, or rejected by the owner.
    t = _title_key(e)
    if kind == "krithi" and any(_norm(_base_title(k.title)) == t and (not raaga or k.raaga == raaga.name) for k in cat.krithis):
        problems.append("already in the catalogue")
    if kind == "raaga" and cat.resolve_raaga(rec.get("name", "")) and cat.resolve_raaga(rec["name"]).name.lower() == rec["name"].lower():
        problems.append("raaga already in the catalogue")
    probe = {**e, "record": rec}
    if find_twin(cat, items, probe):
        problems.append("already waiting for review")
    for x in items:
        if (decisions.get(x.get("id"), {}) or {}).get("status") == "rejected" and find_twin(cat, [{**x, "status": "pending"}], probe):
            problems.append("the owner rejected this song before")
            break
    moods = rec.get("moods") or []
    if not moods:
        problems.append("suggest at least one mood inferred from the song's meaning")
    for m in moods:
        if m not in cat.moods:
            problems.append(f"unknown mood '{m}'")
            continue
        ev = [x for x in e.get("mood_evidence") or [] if x.get("mood") == m]
        if not ev:
            problems.append(f"mood '{m}' needs its basis: the line from the trusted page it was inferred from")
        for x in ev:
            if not (trusted(str(x.get("source", ""))) and len(str(x.get("quote", "")).strip()) >= 20):
                problems.append(f"mood '{m}': the basis must be a quote of 20+ characters from a trusted page")
            if not x.get("needs_curator_confirmation") and not x.get("user_confirmed"):
                problems.append(f"mood '{m}': mark it needs_curator_confirmation (the owner confirms on review)")
        if raaga and m in raaga.avoid_moods:
            problems.append(f"{raaga.name} must never be suggested for '{m}'")
    if not problems:
        # Dry run of approval on a scratch copy: the same validation the real import runs.
        tmp = Path(tempfile.mkdtemp())
        try:
            shutil.copytree(cat_dir(cat), tmp / "data")
            st = ProposalStore(tmp / "p.db", tmp / "data")
            steps = []
            if new_raaga:
                steps.append(("raaga", new_raaga, ["https://www.karnatik.com/"], "waiting raaga, applied first for the dry run", []))
            trial = {**rec, "language": rec.get("language") or "Unknown"} if kind == "krithi" else rec
            mev = [{**x, "user_confirmed": True} for x in e.get("mood_evidence") or []]
            steps.append((kind, trial, list(srcs), e.get("evidence", ""), mev))
            for k, r, sr, ev, me in steps:
                res = st.propose_addition(AGENT, Catalog.load(tmp / "data"), k, r, sr, ev,
                                          me or [{"mood": m, "source": sr[0], "quote": "dry run of a waiting raaga",
                                                  "user_confirmed": True} for m in r.get("moods") or []])
                ap = res if "error" in res else st.approve(res["proposal_id"])
                if "error" in ap:
                    problems.append(ap["error"] if k == kind else f"the waiting raaga doesn't apply cleanly: {ap['error']}")
                    break
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    return {"name": name, "ok": not problems, "problems": problems, "warnings": warnings, "record": rec}


def _waiting_raaga(items: list[dict], decisions: dict, name: str) -> dict | None:
    """A raaga addition in the box, not rejected, with this name or alias."""
    n = _norm(name)
    for x in items:
        rec = x.get("record") or {}
        if x.get("kind") != "raaga" or x.get("type") != "addition":
            continue
        if (decisions.get(x.get("id"), {}) or {}).get("status") == "rejected":
            continue
        names = [rec.get("name", "")] + str(rec.get("aliases") or "").split(";")
        if any(_norm(a) == n for a in names if a.strip()):
            return rec
    return None


def raagas_first(candidates: list[dict]) -> list[dict]:
    """New raagas go before songs, so a song in a new raaga can follow it (and the owner sees the raaga first)."""
    return sorted(candidates, key=lambda c: c.get("kind") != "raaga")


def cat_dir(cat: Catalog) -> Path:
    return getattr(cat, "data_dir", None) or DATA_DIR


def run_check(cat: Catalog, candidates: list[dict], box: dict, decisions: dict) -> list[dict]:
    items = [dict(x) for x in (box or {}).get("items", [])]
    out = []
    for c in raagas_first(candidates):
        r = check_candidate(cat, c, items, (decisions or {}).get("decisions", {}))
        out.append(r)
        if r["ok"]:      # later candidates must not duplicate earlier ones in the same run
            items.append({**c, "record": r["record"], "status": "pending"})
    return out


def waiting_for_owner(items: list[dict], decisions: dict) -> int:
    """Curator-agent suggestions in the box that the owner hasn't decided yet."""
    return sum(1 for x in items if x.get("by") == AGENT
               and (decisions.get(x.get("id")) or {}).get("status", "pending") == "pending")


def run_add(cat: Catalog, candidates: list[dict], box: dict, decisions: dict, uid: str, limit: int) -> tuple[dict, list[dict]]:
    """Add checked candidates. The owner never has more than `limit` curator suggestions waiting:
    a run adds only the room left (nothing once `limit` are waiting)."""
    items = [dict(x) for x in (box or {}).get("items", [])]
    waiting = waiting_for_owner(items, (decisions or {}).get("decisions", {}))
    room = max(0, limit - waiting)
    report, added = [], 0
    for c in raagas_first(candidates):
        r = check_candidate(cat, c, items, (decisions or {}).get("decisions", {}))
        if r["ok"] and added >= room:
            r = {**r, "ok": False, "problems": [f"no room: {waiting} curator suggestions already wait for the owner "
                                                f"and the limit is {limit}"]}
        if r["ok"]:
            entry = {**c, "record": r["record"], "by": AGENT}
            ts = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
            saved, _ = merge_into_box(cat, items, entry, ts, uid)
            r = {**r, "id": saved["id"]}
            added += 1
        report.append({k: v for k, v in r.items() if k != "record"})
    return {"items": items[-200:]}, report


def _load(path: str | None, default):
    return json.loads(Path(path).read_text(encoding="utf-8")) if path else default


def main(argv: list[str]) -> int:
    from .gaps import load_config
    if argv[:1] == ["room"]:
        opts = {argv[i]: argv[i + 1] for i in range(1, len(argv) - 1, 2)}
        box, dec = _load(opts.get("--box"), {"items": []}), _load(opts.get("--decisions"), {"decisions": {}})
        limit = load_config()["max_suggestions_per_run"]
        waiting = waiting_for_owner(box.get("items", []), dec.get("decisions", {}))
        from .gaps import plan
        room = max(0, limit - waiting)
        print(json.dumps({"waiting": waiting, "limit": limit, "room": room, "slots": plan(room)}))
        return 0
    if len(argv) < 2 or argv[0] not in ("check", "add"):
        print(__doc__)
        return 2
    opts = {argv[i]: argv[i + 1] for i in range(2, len(argv) - 1, 2)}
    cands = _load(argv[1], [])
    if isinstance(cands, dict):
        cands = cands.get("items") or cands.get("candidates") or []
    box, dec = _load(opts.get("--box"), {"items": []}), _load(opts.get("--decisions"), {"decisions": {}})
    cat = Catalog.load()
    if argv[0] == "check":
        print(json.dumps([{k: v for k, v in r.items() if k != "record"} for r in run_check(cat, cands, box, dec)],
                         ensure_ascii=False, indent=2))
        return 0
    if "--uid" not in opts or "--out" not in opts:
        print("add needs --uid and --out")
        return 2
    new_box, rep = run_add(cat, cands, box, dec, opts["--uid"], load_config()["max_suggestions_per_run"])
    Path(opts["--out"]).write_text(json.dumps(new_box, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(rep, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
