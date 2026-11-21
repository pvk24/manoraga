"""Import the chat page's suggestion box into the repo, exactly as the page's "Export for the repo" would.

    python scripts/import_box.py BOX.json DECISIONS.json [--all]

BOX.json is the db document `suggestions/<owner id>` ({"items": [...]}) and DECISIONS.json is `curation/decisions`
({"decisions": {...}}), both read from the page's storage with the artifact db tools. The page's own export code
(normEntry + merged, run in Node from web/index.html) turns them into a `manoraga-suggestions/1` export, which is
imported like `python -m carnatic.review import`: accepted and applied entries are approved into data/*.csv,
rejected ones skipped, the rest queued. Entries the page already marked as exported are left out unless --all.
Re-running is safe (idempotent by page id). Afterwards: rebuild the page, run pytest, commit.

Prints the import results and the ids to mark as exported in `curation/decisions`.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from carnatic.page_import import import_export  # noqa: E402
from carnatic.proposals import ProposalStore  # noqa: E402


def page_export(items: list[dict], decisions: dict, include_exported: bool = False) -> dict:
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    if include_exported:
        decisions = {k: {kk: vv for kk, vv in v.items() if kk != "exported"} for k, v in decisions.items()}
    out = subprocess.run(["node", str(ROOT / "tests" / "js_review_runner.js")], capture_output=True, text=True,
                         input=json.dumps({"html": html, "items": items, "decisions": decisions}), check=True)
    return json.loads(out.stdout)


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    box = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    dec = json.loads(Path(argv[1]).read_text(encoding="utf-8")).get("decisions", {})
    export = page_export(box.get("items", []), dec, "--all" in argv)
    results = import_export(ProposalStore(), export)
    print(json.dumps({"exported_ids": [e["id"] for e in export["items"]], "results": results}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
