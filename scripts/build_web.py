"""Build web/index.html (the chat UI) from web/template.html + the CSV catalogue.

    python scripts/build_web.py

The CSVs stay the single source of truth: edit data/, rebuild, republish.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from carnatic.catalog import Catalog  # noqa: E402



def build(write: bool = True) -> str:
    cat = Catalog.load()
    payload = {
        "raagas": [{k: v for k, v in r.__dict__.items()} for r in cat.raagas.values()],
        "krithis": [k.__dict__ for k in cat.krithis],
        "moods": {m.key: {"label": m.label, "when": m.when_to_use, "fallback": m.fallback} for m in cat.moods.values()},
    }
    tpl = (ROOT / "web" / "template.html").read_text(encoding="utf-8")
    assert "/*__CATALOG__*/null" in tpl
    html = tpl.replace("/*__CATALOG__*/null", json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/"))
    html = html.replace("__NRAAGAS__", str(len(cat.raagas))).replace("__NKRITHIS__", str(len(cat.krithis)))
    if write:
        (ROOT / "web" / "index.html").write_text(html, encoding="utf-8")
        print(f"web/index.html: {len(html)//1024} KB, {len(cat.raagas)} raagas, {len(cat.krithis)} krithis")
    return html


if __name__ == "__main__":
    build()
