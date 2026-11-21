"""Friends publish the committed web/index.html into their own Claude accounts, so it must match template + data."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from build_web import build  # noqa: E402


def test_committed_page_is_up_to_date():
    built = build(write=False)
    assert (ROOT / "web" / "index.html").read_text(encoding="utf-8") == built, \
        "web/index.html is stale: run python scripts/build_web.py and commit it"


def test_page_has_nothing_tied_to_one_account():
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    for s in ("claude.ai/artifact/", "a4c59f81", "sk-ant-"):
        assert s not in html


def test_setup_instructions_declare_the_same_capabilities():
    """Friends' copies need every capability the page uses (chat, saved data, review, downloads, web search)."""
    import json
    import re
    setup = (ROOT / "SETUP_IN_CLAUDE.md").read_text(encoding="utf-8")
    skill = (ROOT / ".claude" / "skills" / "install-manoraga" / "SKILL.md").read_text(encoding="utf-8")
    a = json.loads(re.search(r"`(\{\"sample\".*?)`", setup).group(1))
    b = json.loads(re.search(r"```json\n(.*?)\n```", skill, re.S).group(1))
    assert a == b
    assert {"sample", "user", "db", "mcp", "downloads"} <= set(a)
    assert {r["path"] for r in a["db"]["rules"]} == {"suggestions", "suggestions/{self}", "curation", "catalog"}
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    for used in ("use('sample')", "use('db')", "use('user')", "use('mcp')", "use('downloads')", "curation/decisions", "catalog/overlay"):
        assert used in html
