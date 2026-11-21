"""Catalogue change proposals: corrections and additions that wait for the curator's approval.

The agent can only PROPOSE. Approval happens outside the model: `/approve <id>` in the CLI (curator mode) or
`python -m carnatic.review`. Approving writes data/*.csv, re-validates the whole catalogue, and rolls back if
anything is inconsistent.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import shutil
import sqlite3
import time
from pathlib import Path
from urllib.parse import urlparse

import re

from .catalog import DATA_DIR, Catalog, _norm

DEFAULT_DB = Path(__file__).resolve().parent.parent / "proposals.db"
TRUSTED = ("karnatik.com", "shivkumar.org", "rasikas.org", "sangeethapriya.org")

KRITHI_FIELDS = {"title", "raaga", "composer", "language", "tala", "form", "moods", "descriptors", "notes"}
RAAGA_FIELDS = {"name", "aliases", "type", "melakarta_number", "parent", "arohana", "avarohana", "scale_note",
                "foreign_notes", "moods", "rasa", "notes"}
CORRECTABLE = {"krithi": {"raaga", "composer", "language", "tala", "moods"},
               "raaga": {"arohana", "avarohana", "parent", "melakarta_number", "moods"}}


def trusted(url: str) -> bool:
    try:
        host = urlparse(url).hostname or ""
    except ValueError:
        return False
    return urlparse(url).scheme == "https" and any(host == d or host.endswith("." + d) for d in TRUSTED)


def _base_title(t: str) -> str:
    return re.sub(r"\(.*?\)", "", str(t or "")).strip()


def _paren(t: str) -> str:
    m = re.search(r"\(([^)]*)\)", str(t or ""))
    return m.group(1).strip() if m else ""


def _filled(v) -> bool:
    return not (v is None or (isinstance(v, str) and not v.strip()) or (isinstance(v, list) and not v))


def merge_addition(old: dict, new: dict) -> dict:
    """An update to a pending addition: new non-empty values win, nothing is erased, lists are unioned."""
    rec = dict(old.get("record") or {})
    for k, v in (new.get("record") or {}).items():
        if _filled(v):
            rec[k] = v
    for key in ("title", "name"):        # keep a clean title if the update only added "(Raaga)"
        if old.get("record", {}).get(key) and _base_title(rec.get(key)) and \
                _norm(_base_title(rec.get(key))) == _norm(_base_title(old["record"][key])) and "(" not in old["record"][key]:
            rec[key] = old["record"][key]
    srcs = list(old.get("sources") or [])
    srcs += [u for u in new.get("sources") or [] if u not in srcs]
    ev_old, ev_new = (old.get("evidence") or "").strip(), (new.get("evidence") or "").strip()
    evidence = ev_old if not ev_new or ev_new in ev_old else (ev_new if not ev_old else ev_old + " | " + ev_new)
    moods = rec.get("moods") or []
    mev = []
    for e in list(old.get("mood_evidence") or []) + list(new.get("mood_evidence") or []):
        if isinstance(e, dict) and e.get("mood") in moods and not any(
                x.get("mood") == e.get("mood") and x.get("quote") == e.get("quote") for x in mev):
            mev.append(e)
    return {"record": rec, "sources": srcs, "evidence": evidence, "mood_evidence": mev}


class ProposalStore:
    def __init__(self, path: Path | str = DEFAULT_DB, data_dir: Path = DATA_DIR):
        self.data_dir = Path(data_dir)
        self.conn = sqlite3.connect(str(path))
        self.conn.execute("""CREATE TABLE IF NOT EXISTS proposals (
            id INTEGER PRIMARY KEY AUTOINCREMENT, created_at REAL, user_id TEXT, kind TEXT,
            payload TEXT, status TEXT DEFAULT 'pending', decided_at REAL, decision_note TEXT)""")

    # ---- create ---------------------------------------------------------
    def _add(self, user_id: str, kind: str, payload: dict) -> int:
        cur = self.conn.execute("INSERT INTO proposals (created_at, user_id, kind, payload) VALUES (?, ?, ?, ?)",
                                (time.time(), user_id, kind, json.dumps(payload)))
        self.conn.commit()
        return cur.lastrowid

    def propose_correction(self, user_id: str, cat: Catalog, item_type: str, item_name: str, field: str,
                           suggested_value, reason: str, sources: list[str] | None = None,
                           origin: dict | None = None) -> dict:
        if field not in CORRECTABLE.get(item_type, set()):
            return {"error": f"field must be one of {sorted(CORRECTABLE.get(item_type, []))} for a {item_type}"}
        if item_type == "krithi":
            hits = [k for k in cat.krithis if k.title.lower() == item_name.lower()]
            if not hits:
                return {"error": f"no krithi titled '{item_name}' in the catalogue"}
            current = getattr(hits[0], field)
            name = hits[0].title
        else:
            r = cat.resolve_raaga(item_name)
            if not r:
                return {"error": f"no raaga '{item_name}' in the catalogue"}
            current, name = getattr(r, field), r.name
        bad = [u for u in sources or [] if not trusted(u)]
        if bad:
            return {"error": f"sources must be https pages on {', '.join(TRUSTED)}; not trusted: {bad}"}
        if field != "moods" and not sources:
            return {"error": "a factual correction needs at least one trusted source URL"}
        payload = {"item_type": item_type, "item_name": name, "field": field, "current": current,
                   "suggested": suggested_value, "reason": reason, "sources": sources or []}
        if origin:
            payload["origin"] = origin
        # A pending correction of the same field on the same item: update it (latest statement wins).
        prev = next((p for p in self.list("pending") if p["kind"] == "correction"
                     and p["payload"]["item_type"] == item_type and p["payload"]["item_name"] == name
                     and p["payload"]["field"] == field), None)
        if prev:
            old = prev["payload"]
            if field == "moods" and isinstance(old["suggested"], dict) and isinstance(suggested_value, dict):
                rem, add = list(old["suggested"].get("remove", [])), list(old["suggested"].get("add", []))
                for m in suggested_value.get("remove", []):
                    rem = rem + [m] if m not in rem else rem
                    add = [x for x in add if x != m]
                for m in suggested_value.get("add", []):
                    add = add + [m] if m not in add else add
                    rem = [x for x in rem if x != m]
                payload["suggested"] = {"remove": rem, "add": add}
            payload["sources"] = list(old.get("sources") or []) + [u for u in payload["sources"] if u not in (old.get("sources") or [])]
            if old.get("reason") and reason and reason not in old["reason"]:
                payload["reason"] = old["reason"] + " | " + reason
            payload["origin"] = origin or old.get("origin")
            payload["updates"] = list(old.get("updates") or []) + [{"at": time.time(), "by": user_id}]
            if old.get("edits"):
                payload["edits"] = old["edits"]
            self.conn.execute("UPDATE proposals SET payload = ? WHERE id = ?", (json.dumps(payload), prev["id"]))
            self.conn.commit()
            return {"ok": True, "proposal_id": prev["id"], "updated": True,
                    "status": "pending curator approval (updated the earlier proposal)",
                    "change": f"{item_type} '{name}': {field} {current!r} -> {payload['suggested']!r}"}
        pid = self._add(user_id, "correction", payload)
        return {"ok": True, "proposal_id": pid, "status": "pending curator approval",
                "change": f"{item_type} '{name}': {field} {current!r} -> {suggested_value!r}"}

    def propose_addition(self, user_id: str, cat: Catalog, kind: str, record: dict, sources: list[str],
                         evidence: str, mood_evidence: list | None = None, origin: dict | None = None) -> dict:
        if kind not in ("krithi", "raaga"):
            return {"error": "kind must be krithi or raaga"}
        # The same song (or raaga) already waiting for review: update that proposal instead of adding a duplicate.
        update_of = self._pending_addition(cat, kind, record)
        if update_of:
            m = merge_addition(update_of["payload"], {"record": record, "sources": sources, "evidence": evidence,
                                                      "mood_evidence": mood_evidence})
            record, sources, evidence, mood_evidence = m["record"], m["sources"], m["evidence"], m["mood_evidence"]
            origin = origin or update_of["payload"].get("origin")
        if not sources or not all(trusted(u) for u in sources):
            return {"error": f"at least one source, all https pages on {', '.join(TRUSTED)}"}
        if len((evidence or "").strip()) < 20:
            return {"error": "evidence must quote what the source page says (raaga, composer, tala ...)"}
        allowed = KRITHI_FIELDS if kind == "krithi" else RAAGA_FIELDS
        extra = set(record) - allowed
        if extra:
            return {"error": f"unknown fields {sorted(extra)}; allowed: {sorted(allowed)}"}
        if kind == "krithi":
            missing = [f for f in ("title", "raaga", "composer", "language") if not str(record.get(f, "")).strip()]
            if missing:
                return {"error": f"missing {missing}; use the source's values, never guess"}
            if any(k.title.lower() == record["title"].strip().lower() for k in cat.krithis):
                return {"error": f"'{record['title']}' is already in the catalogue"}
            r = cat.resolve_raaga(record["raaga"])
            if not r:
                pending = [p for p in self.list("pending") if p["kind"] == "add_raaga"
                           and p["payload"]["record"]["name"].lower() == record["raaga"].strip().lower()]
                if not pending:
                    return {"error": f"raaga '{record['raaga']}' is not in the catalogue: propose the raaga first"}
            else:
                record = {**record, "raaga": r.name}
        else:
            missing = [f for f in ("name", "type", "arohana", "avarohana") if not str(record.get(f, "")).strip()]
            if missing:
                return {"error": f"missing {missing}; use the source's values, never guess"}
            if cat.resolve_raaga(record["name"]) and cat.resolve_raaga(record["name"]).name.lower() == record["name"].lower():
                return {"error": f"raaga '{record['name']}' is already in the catalogue"}
        for f in ("moods",):
            if f in record:
                vals = record[f] if isinstance(record[f], list) else [x for x in str(record[f]).split(";") if x]
                bad = [m for m in vals if m not in cat.moods]
                if bad:
                    return {"error": f"unknown mood keys {bad}"}
                record[f] = vals
        # Moods of a new song (owner's rule): the agent infers them from what the trusted page says about the song
        # (meaning, rasa, when it is sung), suggests them, and the USER validates. So every proposed mood needs its basis
        # (a quote from a trusted page, or the user's own words) and the user's confirmation.
        mood_evidence = list(mood_evidence or [])
        moods = record.get("moods") or []
        for m in moods:
            ev = [e for e in mood_evidence if isinstance(e, dict) and e.get("mood") == m]
            if not ev:
                return {"error": f"mood '{m}' has no basis: give the source text you inferred it from (or the user's "
                                 "words), or leave it out for the curator to decide"}
            for e in ev:
                src, quote, about = str(e.get("source", "")), str(e.get("quote", "")).strip(), e.get("about", "song")
                if src not in ("user", "curator") and not trusted(src):
                    return {"error": f"the basis for '{m}' must be 'user' or an https page on {', '.join(TRUSTED)}"}
                if len(quote) < (3 if src in ("user", "curator") else 20):
                    return {"error": f"the basis for '{m}' needs the actual words (quote)"}
                if about not in ("song", "raaga"):
                    return {"error": "mood evidence 'about' must be 'song' or 'raaga'"}
                if src not in ("user", "curator") and e.get("user_confirmed") is not True \
                        and e.get("needs_curator_confirmation") is not True:
                    return {"error": f"mood '{m}' is your inference: show it to the user with its basis and propose it "
                                     "only after they confirm (user_confirmed: true)"}
        extra_ev = [e for e in mood_evidence if isinstance(e, dict) and e.get("mood") not in moods]
        if extra_ev:
            return {"error": f"mood evidence given for moods not in the record: {sorted({e.get('mood') for e in extra_ev})}"}
        payload = {"record": record, "sources": sources, "evidence": evidence, "mood_evidence": mood_evidence}
        if origin:
            payload["origin"] = origin
        if update_of:
            old = update_of["payload"]
            for k in ("edits",):
                if old.get(k):
                    payload[k] = old[k]
            payload["updates"] = list(old.get("updates") or []) + [{"at": time.time(), "by": user_id}]
            self.conn.execute("UPDATE proposals SET payload = ? WHERE id = ?", (json.dumps(payload), update_of["id"]))
            self.conn.commit()
            return {"ok": True, "proposal_id": update_of["id"], "updated": True,
                    "status": "pending curator approval (updated the earlier proposal)", "record": record}
        pid = self._add(user_id, f"add_{kind}", payload)
        return {"ok": True, "proposal_id": pid, "status": "pending curator approval", "record": record}

    def _pending_addition(self, cat: Catalog, kind: str, record: dict) -> dict | None:
        """The pending addition this one updates: same kind and title (ignoring "(Raaga)"), and for a krithi a
        compatible raaga. None if there is no match, or more than one and the raaga doesn't pick one."""
        key = "name" if kind == "raaga" else "title"
        title = _norm(_base_title(record.get(key) or ""))
        if not title:
            return None

        def raaga_of(rec):
            cand = rec.get("raaga") or _paren(rec.get(key))
            r = cat.resolve_raaga(cand) if cand else None
            return r.name if r else str(cand or "").strip().lower()

        cands = [p for p in self.list("pending") if p["kind"] == f"add_{kind}"
                 and _norm(_base_title(p["payload"]["record"].get(key) or "")) == title]
        if kind == "krithi" and cands:
            mine = raaga_of(record)
            exact = [p for p in cands if mine and raaga_of(p["payload"]["record"]) == mine]
            if exact:
                cands = exact
            elif mine:
                cands = [p for p in cands if not raaga_of(p["payload"]["record"])]
        return cands[0] if len(cands) == 1 else None

    # ---- read -----------------------------------------------------------
    def list(self, status: str | None = "pending") -> list[dict]:
        q = "SELECT id, created_at, user_id, kind, payload, status, decision_note FROM proposals"
        rows = self.conn.execute(q + (" WHERE status = ?" if status else "") + " ORDER BY id",
                                 (status,) if status else ()).fetchall()
        return [{"id": i, "created_at": c, "user_id": u, "kind": k, "payload": json.loads(p), "status": s,
                 "decision_note": n} for i, c, u, k, p, s, n in rows]

    def get(self, pid: int) -> dict | None:
        return next((p for p in self.list(None) if p["id"] == pid), None)

    # ---- decide (curator only; never exposed as an agent tool) -----------
    # ---- edit (curator only) --------------------------------------------
    def edit(self, pid: int, changes: dict, note: str = "") -> dict:
        """Correct a pending proposal before approving it. Additions: any record field (moods as a list or
        'a;b'). Corrections: 'suggested' (or 'remove'/'add' for a moods correction). Logged in the payload."""
        p = self.get(pid)
        if not p or p["status"] != "pending":
            return {"error": f"proposal {pid} is not pending"}
        if not changes:
            return {"error": "nothing to change, e.g. tala=\"Misra Chapu\" moods=calm_anxious;comfort_when_low"}
        cat = Catalog.load(self.data_dir)
        pay = p["payload"]
        as_list = lambda v: v if isinstance(v, list) else [x.strip() for x in str(v).split(";") if x.strip()]
        if p["kind"] in ("add_krithi", "add_raaga"):
            allowed = KRITHI_FIELDS if p["kind"] == "add_krithi" else RAAGA_FIELDS
            bad = set(changes) - allowed
            if bad:
                return {"error": f"unknown fields {sorted(bad)}; allowed: {sorted(allowed)}"}
            rec = dict(pay["record"])
            for k, v in changes.items():
                if k == "moods":
                    v = as_list(v)
                    unknown = [m for m in v if m not in cat.moods]
                    if unknown:
                        return {"error": f"unknown mood keys {unknown}; valid: {sorted(cat.moods)}"}
                    kept = [e for e in pay.get("mood_evidence") or [] if e.get("mood") in v]
                    have = {e["mood"] for e in kept}
                    kept += [{"mood": m, "source": "curator", "quote": note or "set by the curator"} for m in v if m not in have]
                    pay["mood_evidence"] = kept
                elif k == "raaga" and p["kind"] == "add_krithi":
                    r = cat.resolve_raaga(v)
                    if not r:
                        return {"error": f"raaga '{v}' is not in the catalogue"}
                    v = r.name
                rec[k] = v
            pay["record"] = rec
        else:
            if pay["field"] == "moods":
                cur = pay["suggested"] if isinstance(pay["suggested"], dict) else {"remove": [], "add": as_list(pay["suggested"])}
                for k in ("remove", "add"):
                    if k in changes:
                        cur[k] = as_list(changes[k])
                        unknown = [m for m in cur[k] if m not in cat.moods]
                        if unknown:
                            return {"error": f"unknown mood keys {unknown}"}
                if set(changes) - {"remove", "add"}:
                    return {"error": "for a moods correction, change remove=... and/or add=..."}
                pay["suggested"] = cur
            else:
                if set(changes) != {"suggested"}:
                    return {"error": "for this correction, change suggested=..."}
                pay["suggested"] = changes["suggested"]
        pay.setdefault("edits", []).append({"changes": changes, "note": note, "at": time.time()})
        self.conn.execute("UPDATE proposals SET payload = ? WHERE id = ?", (json.dumps(pay), pid))
        self.conn.commit()
        return {"ok": True, "proposal_id": pid, "status": "pending", "payload": pay}

    def reject(self, pid: int, note: str = "") -> dict:
        p = self.get(pid)
        if not p or p["status"] != "pending":
            return {"error": f"proposal {pid} is not pending"}
        self._decide(pid, "rejected", note)
        return {"ok": True, "proposal_id": pid, "status": "rejected"}

    def approve(self, pid: int, note: str = "") -> dict:
        p = self.get(pid)
        if not p or p["status"] != "pending":
            return {"error": f"proposal {pid} is not pending"}
        backup = {f: (self.data_dir / f).read_text(encoding="utf-8") for f in ("raagas.csv", "krithis.csv")}
        try:
            self._apply(p)
            Catalog.load(self.data_dir)          # full validation; raises on any inconsistency
        except Exception as e:  # noqa: BLE001 - roll back on anything
            for f, text in backup.items():
                (self.data_dir / f).write_text(text, encoding="utf-8")
            return {"error": f"not applied, catalogue unchanged: {e}"}
        self._decide(pid, "approved", note)
        return {"ok": True, "proposal_id": pid, "status": "approved"}

    def _decide(self, pid, status, note):
        self.conn.execute("UPDATE proposals SET status = ?, decided_at = ?, decision_note = ? WHERE id = ?",
                          (status, time.time(), note, pid))
        self.conn.commit()

    def _rows(self, name):
        path = self.data_dir / name
        with open(path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        return path, rows, list(rows[0].keys())

    def _write(self, path, fields, rows):
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")   # match the repo files
            w.writeheader()
            w.writerows(rows)
        shutil.move(tmp, path)

    def _apply(self, p: dict):
        today = dt.date.today().isoformat()
        pay = p["payload"]
        stamp = f"Added via ManoRaga proposal #{p['id']} on {today} (sources checked by the agent; approved by curator)"
        if p["kind"] in ("add_krithi", "add_raaga"):
            fname = "krithis.csv" if p["kind"] == "add_krithi" else "raagas.csv"
            path, rows, fields = self._rows(fname)
            rec = dict(pay["record"])
            row = {f: "" for f in fields}
            for k, v in rec.items():
                row[k] = ";".join(v) if isinstance(v, list) else str(v)
            row["sources"] = ";".join(pay["sources"])
            mev = pay.get("mood_evidence") or []
            def basis(e):
                if e["source"] in ("user", "curator"):
                    return e["source"]
                who = ("found by the curator agent, confirmed by the curator" if e.get("confirmed_by") == "curator" or not e.get("user_confirmed")
                       else "user-confirmed")
                return "inferred from " + e["source"] + ", " + who + (", raaga-level" if e.get("about") == "raaga" else "")
            parts = list(dict.fromkeys(f"{e['mood']} ({basis(e)})" for e in mev))   # one line per mood + basis
            mood_note = ("Moods from: " + "; ".join(parts)) if parts else ""
            edits = pay.get("edits") or []
            edit_note = ("Curator edited: " + ", ".join(sorted({k for e in edits for k in e["changes"]}))) if edits else ""
            row["notes"] = "; ".join(x for x in (row.get("notes", ""), mood_note, edit_note, stamp) if x)
            for u in {e["source"] for e in mev if e.get("source") not in ("user", "curator")} - set(pay["sources"]):
                row["sources"] += ";" + u
            row["verified"] = "false"           # owner can flip it after their own review
            if p["kind"] == "add_krithi":
                row["form"] = row.get("form") or "krithi"
            rows.append(row)
            self._write(path, fields, rows)
        elif p["kind"] == "correction":
            fname = "krithis.csv" if pay["item_type"] == "krithi" else "raagas.csv"
            key = "title" if pay["item_type"] == "krithi" else "name"
            path, rows, fields = self._rows(fname)
            row = next(r for r in rows if r[key].lower() == pay["item_name"].lower())
            new = pay["suggested"]
            if pay["field"] == "moods":
                cur = [m for m in row["moods"].split(";") if m]
                if isinstance(new, dict):     # {"remove": [...], "add": [...]}
                    cur = [m for m in cur if m not in new.get("remove", [])] + \
                          [m for m in new.get("add", []) if m not in cur]
                    avoid = [m for m in row.get("avoid_moods", "").split(";") if m]
                    avoid += [m for m in new.get("remove", []) if m not in avoid and m not in cur]
                    row["avoid_moods"] = ";".join(avoid)
                else:
                    cur = list(new)
                row["moods"] = ";".join(cur)
            else:
                old = row[pay["field"]]
                row[pay["field"]] = str(new)
                note = f"{pay['field']} changed from '{old}' via proposal #{p['id']} on {today}: {pay['reason']}"
                row["notes"] = "; ".join(x for x in (row.get("notes", ""), note) if x)
            if pay.get("sources"):
                srcs = [s for s in row.get("sources", "").split(";") if s]
                row["sources"] = ";".join(srcs + [s for s in pay["sources"] if s not in srcs])
            self._write(path, fields, rows)
        else:
            raise ValueError(f"unknown proposal kind {p['kind']}")
