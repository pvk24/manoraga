"""Curator review of proposed catalogue changes (the agent can only propose):

    python -m carnatic.review                 # list pending proposals
    python -m carnatic.review show 3
    python -m carnatic.review edit 3 tala="Misra Chapu" moods="calm_anxious;comfort_when_low"
    python -m carnatic.review approve 3 "checked on Karnatik.com"
    python -m carnatic.review reject 4 "wrong raaga"
    python -m carnatic.review import manoraga-suggestions.json   # the chat page's Review > Export file

After approving, rebuild and republish the web page (python scripts/build_web.py).
"""
import json
import shlex
import sys

from .page_import import import_file
from .proposals import ProposalStore


def parse_changes(args: list[str]) -> tuple[dict, str]:
    """key=value pairs (quote values with spaces); a trailing note="..." is kept as the edit note."""
    changes, note = {}, ""
    for a in args:
        if "=" not in a:
            raise ValueError(f"expected key=value, got {a!r}")
        k, v = a.split("=", 1)
        if k == "note":
            note = v
        else:
            changes[k.strip()] = v.strip()
    return changes, note


def edit_command(store: ProposalStore, text: str) -> dict:
    """'3 tala="Misra Chapu" moods=a;b note="..."' -> store.edit(...)"""
    parts = shlex.split(text)
    if not parts or not parts[0].isdigit():
        return {"error": 'usage: edit <id> field=value ... e.g. edit 3 tala="Misra Chapu" moods="calm_anxious;comfort_when_low"'}
    try:
        changes, note = parse_changes(parts[1:])
    except ValueError as e:
        return {"error": str(e)}
    return store.edit(int(parts[0]), changes, note)


def describe(p: dict) -> str:
    pay = p["payload"]
    if p["kind"] == "correction":
        head = f"#{p['id']} correction  {pay['item_type']} '{pay['item_name']}'  {pay['field']}: {pay['current']!r} -> {pay['suggested']!r}"
        body = f"    reason: {pay['reason']}"
    else:
        head = f"#{p['id']} {p['kind']}  " + json.dumps(pay["record"], ensure_ascii=False)
        body = f"    evidence: {pay['evidence']}"
    origin = pay.get("origin") or {}
    if origin:
        head += f"   [from the chat page, {origin.get('page_status', 'pending')} there" + \
                (f": {origin['curator_note']}" if origin.get("curator_note") else "") + "]"
    srcs = "\n".join(f"    source: {s}" for s in pay.get("sources", [])) or "    source: (none: mood correction from the user)"
    moods = "\n".join(
        f"    mood {e.get('mood')}: " + ("user's words" if e.get("source") == "user" else
                                       f"inferred from {e.get('source')} ({e.get('about', 'song')}-level), user-confirmed")
        + f"\n      basis: \"{e.get('quote', '')}\"" for e in pay.get("mood_evidence") or [])
    edits = "\n".join(f"    edited: {json.dumps(e['changes'], ensure_ascii=False)}" + (f" ({e['note']})" if e.get("note") else "")
                      for e in pay.get("edits") or [])
    return "\n".join(x for x in (head, body, srcs, moods, edits) if x)


def main(argv: list[str]) -> int:
    store = ProposalStore()
    cmd = argv[0] if argv else "list"
    if cmd == "list":
        pending = store.list("pending")
        print("\n".join(describe(p) for p in pending) or "No pending proposals.")
    elif cmd == "show":
        p = store.get(int(argv[1]))
        print(describe(p) if p else "No such proposal.")
    elif cmd == "edit":
        res = edit_command(store, shlex.join(argv[1:]))
        print(describe(store.get(int(argv[1]))) if res.get("ok") else res["error"])
    elif cmd == "import":
        for r in import_file(store, argv[1]):
            print(r)
    elif cmd in ("approve", "reject"):
        pid, note = int(argv[1]), " ".join(argv[2:])
        print(getattr(store, cmd)(pid, note))
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
