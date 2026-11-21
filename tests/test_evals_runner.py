"""Offline tests for the eval runner's scoring (no API calls)."""
from evals.run_evals import load_cases, score

PASS = lambda case, answer, calls: {"pass": True, "reason": "ok"}  # noqa: E731
FAIL = lambda case, answer, calls: {"pass": False, "reason": "states a fact without a source"}  # noqa: E731


def case(id_):
    return next(c for c in load_cases() if c["id"] == id_)


def test_cases_file_is_well_formed():
    cases = load_cases()
    assert len(cases) >= 23 and len({c["id"] for c in cases}) == len(cases)
    for c in cases:
        assert ("q" in c) != ("turns" in c), c["id"]
        assert c.get("cat") in {"facts", "grounding", "concepts", "moods", "taste", "safety", "scope"}, c["id"]


def test_fact_needs_tool_keyword_and_citation():
    c = case("fact-01")
    ok = "Vatapi Ganapatim is in Hamsadhwani. Source: Karnatik.com https://karnatik.com/c6029.shtml"
    assert score(c, ok, ["search_krithis"], {})["pass"]
    assert "no source cited" in score(c, "It is in Hamsadhwani.", ["search_krithis"], {})["fails"]
    assert not score(c, ok, [], {})["pass"]  # answered without looking it up


def test_grounding_needs_search_or_links_and_grader():
    c = case("ground-01")
    r = score(c, "I couldn't verify that.", ["search_krithis"], {}, PASS)
    assert not r["pass"] and any("none of" in f for f in r["fails"])
    assert score(c, "According to Karnatik.com it's Abheri.", ["search_krithis", "web_search"], {}, PASS)["pass"]
    assert not score(c, "It's Abheri.", ["search_krithis", "web_search"], {}, FAIL)["pass"]


def test_rubric_cases_cannot_pass_without_grader():
    r = score(case("safety-01"), "I'm sorry you're feeling this way...", [], {}, None)
    assert not r["pass"] and "rubric not graded (--no-grader)" in r["fails"]


def test_profile_expectations():
    c = case("pref-01")
    good = {"preferences": {"level": "beginner", "languages": ["Tamil"]}}
    assert score(c, "Noted!", ["set_preference"], good)["pass"]
    as_string = {"preferences": {"level": "Beginner", "languages": "Tamil"}}
    assert score(c, "Noted!", ["set_preference"], as_string)["pass"]
    r = score(c, "Noted!", ["set_preference"], {"preferences": {"level": "beginner"}})
    assert not r["pass"] and any("languages" in f for f in r["fails"])


def test_multi_turn_learning_case():
    c = case("learn-01")
    prof = {"dislikes": {"raaga": ["Thodi"]}}
    calls = ["record_feedback", "recommend"]
    assert score(c, "Try Shubhapantuvarali: Ennalu Urake.", calls, prof)["pass"]
    assert not score(c, "Try Thodi: Kaddanu Variki.", calls, prof)["pass"]


def test_scope_cases_cover_declines_and_allowed_edges():
    scope = [c for c in load_cases() if c["cat"] == "scope"]
    assert sum("declines" in c["rubric"] for c in scope) >= 3       # off-topic must be declined
    assert sum("Fails if it declines" in c["rubric"] for c in scope) >= 2  # borderline in-scope must still be answered


def test_scope_rule_in_both_agents(tmp_path, monkeypatch):
    from pathlib import Path
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    from carnatic.agent import CarnaticAgent
    from carnatic.profile import ProfileStore
    prompt = CarnaticAgent(profiles=ProfileStore(tmp_path / "p.db"))._system()
    page = (Path(__file__).resolve().parent.parent / "web" / "template.html").read_text()
    for text in (prompt, page):
        assert "decline anything else" in text and "never just decline" in text


def test_agent_name_is_manoraga(tmp_path, monkeypatch):
    from pathlib import Path
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    from carnatic.agent import CarnaticAgent
    from carnatic.profile import ProfileStore
    root = Path(__file__).resolve().parent.parent
    assert CarnaticAgent(profiles=ProfileStore(tmp_path / "p.db"))._system().startswith("You are ManoRaga")
    page = (root / "web" / "template.html").read_text()
    assert "<title>ManoRaga</title>" in page and "You are ManoRaga" in page
    assert not [p for p in root.rglob("*") if p.is_file() and p.suffix in {".py", ".md", ".html"}
                and p.name != "test_evals_runner.py" and "Raaga Mitra" in p.read_text(errors="ignore")]


def test_forbid_tools_and_override_profile_checks():
    c = case("corr-01")
    prof = {"mood_overrides": {"krithi|jagadoddharana": {"remove": ["energise_motivate"], "add": []}}}
    assert score(c, "Noted for you; the curator will review it.", ["report_correction"], prof, PASS)["pass"]
    r = score(c, "Noted.", ["report_correction", "record_feedback"], prof, PASS)
    assert not r["pass"] and any("should not call" in f for f in r["fails"])
    r = score(c, "Noted.", ["report_correction"], {"mood_overrides": {}}, PASS)
    assert not r["pass"] and any("missing" in f for f in r["fails"])
