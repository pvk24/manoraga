"""Run the eval set against the live agent:

    python -m evals.run_evals                 # all cases
    python -m evals.run_evals --only fact     # cases whose id starts with "fact"
    python -m evals.run_evals --no-grader     # skip LLM-graded rubrics (cheaper; rubric cases then can't pass)

Each case runs in a fresh agent with a throwaway taste profile. A case passes only if EVERY check it declares passes:
  expect_tools     all of these tools were called
  expect_any_tool  at least one of these was called (e.g. web_search OR source_links)
  forbid_tools     none of these was called (e.g. record_feedback for a correction)
  must_include_*   keywords present (any / all); must_not_include: keywords absent
  cite             the answer names a trusted source (Karnatik.com, Shivkumar.org, Rasikas.org, Sangeethapriya.org, Wikipedia)
  expect_profile   the saved taste profile contains what the user said
  rubric           an LLM grader judges the reply against a written rubric
  turns            multi-turn conversation; checks apply to the final reply
Results are saved to evals/results/<timestamp>.json so runs can be compared over time.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
import time
from collections import defaultdict
from pathlib import Path

CASES = Path(__file__).with_name("cases.jsonl")
RESULTS = Path(__file__).with_name("results")
SOURCES_RE = re.compile(r"karnatik\.com|shivkumar\.org|rasikas\.org|sangeethapriya\.org|wikipedia\.org|wikipedia", re.I)

GRADER_PROMPT = """You are grading one reply from a Carnatic music assistant against a rubric. Be strict and literal.

Conversation (user turns):
{turns}

Tools the assistant called: {tools}

Assistant's final reply:
<reply>
{reply}
</reply>

Rubric:
{rubric}

Respond with only JSON: {{"pass": true or false, "reason": "<one sentence>"}}"""


def load_cases(only: str | None = None) -> list[dict]:
    cases = [json.loads(line) for line in CASES.read_text().splitlines() if line.strip()]
    return [c for c in cases if not only or c["id"].startswith(only)]


def _get(d, path):
    for part in path.split("."):
        d = d.get(part) if isinstance(d, dict) else None
    return d


def check_profile(profile: dict, expectations: list[dict]) -> list[str]:
    fails = []
    for e in expectations:
        if "|" in e["path"]:                      # keys like mood_overrides.krithi|jagadoddharana
            head, _, last = e["path"].rpartition(".")
            val = (_get(profile, head) or {}).get(last) if head else profile.get(last)
        else:
            val = _get(profile, e["path"])
        if e.get("exists") and not val:
            fails.append(f"profile {e['path']} missing")
            continue
        if "equals" in e and str(val or "").lower() != e["equals"].lower():
            fails.append(f"profile {e['path']} = {val!r}, expected {e['equals']!r}")
        if "contains" in e:
            items = [val] if isinstance(val, str) else list(val or [])
            if not any(e["contains"].lower() in str(x).lower() for x in items):
                fails.append(f"profile {e['path']} = {val!r}, expected to contain {e['contains']!r}")
    return fails


def score(case: dict, answer: str, calls: list[str], profile: dict, grade=None) -> dict:
    """Pure scoring function (unit-tested in tests/test_evals_runner.py)."""
    fails, low = [], answer.lower()
    missing = [t for t in case.get("expect_tools", []) if t not in calls]
    if missing:
        fails.append(f"tools not called: {missing}")
    called_forbidden = [t for t in case.get("forbid_tools", []) if t in calls]
    if called_forbidden:
        fails.append(f"should not call {called_forbidden}")
    if case.get("expect_any_tool") and not any(t in calls for t in case["expect_any_tool"]):
        fails.append(f"none of {case['expect_any_tool']} called")
    if case.get("must_include_any") and not any(s.lower() in low for s in case["must_include_any"]):
        fails.append(f"none of {case['must_include_any']} in answer")
    absent = [s for s in case.get("must_include_all", []) if s.lower() not in low]
    if absent:
        fails.append(f"missing {absent}")
    present = [s for s in case.get("must_not_include", []) if s.lower() in low]
    if present:
        fails.append(f"should not mention {present}")
    if case.get("cite") and not SOURCES_RE.search(answer):
        fails.append("no source cited")
    if case.get("expect_profile"):
        fails += check_profile(profile, case["expect_profile"])
    grader = None
    if case.get("rubric"):
        if grade is None:
            fails.append("rubric not graded (--no-grader)")
        else:
            grader = grade(case, answer, calls)
            if not grader["pass"]:
                fails.append(f"grader: {grader['reason']}")
    return {"id": case["id"], "cat": case.get("cat", "other"), "pass": not fails, "fails": fails,
            "grader": grader, "tools": calls, "answer": answer}


def make_grader(client, model: str):
    def grade(case, answer, calls):
        turns = case.get("turns") or [case["q"]]
        prompt = GRADER_PROMPT.format(turns="\n".join(f"- {t}" for t in turns), tools=calls or "none",
                                      reply=answer, rubric=case["rubric"])
        resp = client.messages.create(model=model, max_tokens=200, messages=[{"role": "user", "content": prompt}])
        raw = "".join(b.text for b in resp.content if b.type == "text")
        m = re.search(r"\{.*\}", raw, re.S)
        try:
            out = json.loads(m.group(0)) if m else {}
            return {"pass": bool(out.get("pass")), "reason": str(out.get("reason", ""))[:300]}
        except json.JSONDecodeError:
            return {"pass": False, "reason": f"grader returned unparseable output: {raw[:120]!r}"}
    return grade


def main():
    from dotenv import load_dotenv
    load_dotenv()
    import anthropic

    from carnatic.agent import MODEL, CarnaticAgent
    from carnatic.catalog import Catalog
    from carnatic.profile import ProfileStore
    from carnatic.proposals import ProposalStore

    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    ap.add_argument("--no-grader", action="store_true")
    args = ap.parse_args()

    grade = None if args.no_grader else make_grader(anthropic.Anthropic(), os.getenv("CARNATIC_GRADER_MODEL", MODEL))
    cat, results = Catalog.load(), []
    for c in load_cases(args.only):
        with tempfile.TemporaryDirectory() as d:
            store = ProfileStore(Path(d) / "p.db")
            proposals = ProposalStore(Path(d) / "proposals.db")   # throwaway queue; evals never approve anything
            agent = CarnaticAgent(user_id="eval", catalog=cat, profiles=store, proposals=proposals)
            answer = ""
            for turn in c.get("turns") or [c["q"]]:
                answer = agent.ask(turn)
            r = score(c, answer, list(agent.tools.calls), store.get("eval"), grade)
            r["proposals"] = proposals.list(None)
        results.append(r)
        print(f"{'PASS' if r['pass'] else 'FAIL'}  {r['id']:<11} tools={r['tools']}")
        for f in r["fails"]:
            print(f"        - {f}")

    by = defaultdict(lambda: [0, 0])
    for r in results:
        by[r["cat"]][0] += r["pass"]
        by[r["cat"]][1] += 1
    print("\n" + "  ".join(f"{k}: {p}/{n}" for k, (p, n) in by.items()))
    total = sum(r["pass"] for r in results)
    print(f"TOTAL {total}/{len(results)}")
    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / f"{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps({"model": MODEL, "results": results}, indent=1))
    print(f"saved {out}")


if __name__ == "__main__":
    main()
