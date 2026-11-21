"""Parity: the web page's JavaScript agent core must give the same answers as the Python agent.

Builds the page from the current template + CSVs (no stale web/index.html), runs ~120 tool calls through
both implementations with identical inputs and taste profiles, and compares normalised results.
Needs Node.js; skipped if `node` isn't installed.
"""
import itertools
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from build_web import build  # noqa: E402
from carnatic.catalog import Catalog  # noqa: E402
from carnatic.profile import ProfileStore  # noqa: E402
from carnatic.tools import Toolbox  # noqa: E402

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="Node.js not installed")

CAT = Catalog.load()
MOODS = list(CAT.moods)

# Taste profiles applied before a call: (label, setup steps)
PROFILES = [
    ("new user", []),
    ("dislikes Thodi", [("record_feedback", {"item_type": "raaga", "item_name": "Thodi", "signal": -1})]),
    ("likes Kapi + Tamil", [("record_feedback", {"item_type": "raaga", "item_name": "Kapi", "signal": 1}),
                            ("set_preference", {"key": "languages", "value": ["Tamil"]})]),
    ("languages as a plain string", [("set_preference", {"key": "languages", "value": "Sanskrit"})]),
    ("favourite composer Dikshitar", [("set_preference", {"key": "favourite_composers", "value": ["Dikshitar"]})]),
    ("dislikes Tyagaraja", [("record_feedback", {"item_type": "composer", "item_name": "Tyagaraja", "signal": -1})]),
    ("dislikes a krithi", [("record_feedback", {"item_type": "krithi", "item_name": "Mahaganapatim", "signal": -1})]),
    ("loves Pranav's favourites", [("record_feedback", {"item_type": "krithi", "item_name": t, "signal": 1}) for t in
                                   ["Raghuvamsa Sudha", "Nagumomu", "Vatapi Ganapatim", "Pibare Rama Rasam"]]),
    ("note: Jagadoddharana is soothing, not upbeat", [("report_correction", {"item_type": "krithi", "item_name": "jagadoddharana",
        "remove_moods": ["energise_motivate", "light_playful"], "add_moods": ["calm_anxious"], "reason": "soothing"})]),
    ("note: Kapi (raaga) not romantic for me", [("report_correction", {"item_type": "raaga", "item_name": "Kapi",
        "remove_moods": ["romantic_nostalgic"], "reason": "x"})]),
    ("note: changed mind twice", [("report_correction", {"item_type": "krithi", "item_name": "Odi Baarayya", "remove_moods": ["energise_motivate"], "reason": "x"}),
                                  ("report_correction", {"item_type": "krithi", "item_name": "Odi Baarayya", "add_moods": ["energise_motivate", "joyful_celebrate"], "reason": "y"})]),
    ("changed mind on Thodi", [("record_feedback", {"item_type": "raaga", "item_name": "Thodi", "signal": -1}),
                               ("record_feedback", {"item_type": "raaga", "item_name": "Thodi", "signal": 1})]),
]

LOOKUPS = ["Sankarabharanam", "dheerasankarabharanam", "Todi", "Hamsadhvani", "kamboji", "Naata", "Kadanakuthuhala",
           "Hamsanada", "Bhairavi", "Shanmugapriya", "Mohana", "Kalyan", "Sindhu bhairavi", "Zorbulu", "Varamu"]
SEARCHES = [{"title": t} for t in ["vatapi", "Vathapi Ganapathim", "Endaromahanubhavulu", "Nagumomu", "Marivere",
                                   "Rama nee samana", "Bantu reeti", "zzz",
                                   "Marivere Dikkevvaru", "Marivere Dikkevarayya", "Sri Valli", "Endaro Mahanubhavalu"]] + \
           [{"raaga": r} for r in ["Kalyani", "Nattai", "Todi", "Sankarabharanam", "Nowhere"]] + \
           [{"composer": c} for c in ["Dikshitar", "Syama Sastri", "Purandara", "Swathi"]] + \
           [{"raaga": "Kharaharapriya", "composer": "Tyagaraja"}, {"raaga": "Kambhoji", "title": "Rangasayee"}]


def cases():
    out = []
    for name in LOOKUPS:
        out.append({"label": f"lookup {name}", "tool": "lookup_raaga", "args": {"name": name}})
    for args in SEARCHES:
        out.append({"label": f"search {args}", "tool": "search_krithis", "args": args})
    for (plabel, setup), mood in itertools.product(PROFILES, MOODS):
        out.append({"label": f"{plabel} / {mood}", "setup": setup, "tool": "recommend", "args": {"moods": [mood], "limit": 6}})
    for a, b in [("comfort_when_low", "devotional_reflective"), ("energise_motivate", "joyful_celebrate"),
                 ("calm_anxious", "wind_down_sleep"), ("intense_dramatic", "sit_with_sadness")]:
        out.append({"label": f"pair {a}+{b}", "tool": "recommend", "args": {"moods": [a, b], "limit": 4}})
    for lang, moods in itertools.product(["Kannada", "Tamil", "sanskrit", "Telugu", "Hindi"],
                                         [["energise_motivate", "joyful_celebrate"], ["comfort_when_low"], ["devotional_reflective"], ["light_playful"]]):
        out.append({"label": f"{lang} {moods}", "tool": "recommend", "args": {"moods": moods, "language": lang, "limit": 4}})
    for args in [{"item_type": "krithi", "item_name": "jagadoddharana", "remove_moods": ["energise_motivate"], "reason": "x"},
                 {"item_type": "raaga", "item_name": "Sankarabharanam", "add_moods": ["light_playful"], "reason": "x"},
                 {"item_type": "krithi", "item_name": "Not A Song", "remove_moods": ["energise_motivate"], "reason": "x"},
                 {"item_type": "krithi", "item_name": "Nagumomu", "reason": "x"}]:
        out.append({"label": f"correction {args['item_name']}", "tool": "report_correction", "args": args})
    for q in ["Bhajare re manasa", "Thodi ata tala varnam", "Who is Venkatamakhin?", "Raghuvamsa (sudha)!*'"]:
        out.append({"label": f"links {q}", "tool": "source_links", "args": {"query": q}})
    # Closest-mood fallback: every mood has songs now, so empty one for this user with a personal note.
    no_sleep = [("report_correction", {"item_type": "krithi", "item_name": "Uyyala Loogavayya", "remove_moods": ["wind_down_sleep"], "reason": "not sleepy for me"})]
    for lang in (None, "Telugu", "Kannada", "Tamil", "Sanskrit"):
        out.append({"label": f"fallback wind_down_sleep {lang}", "setup": no_sleep, "tool": "recommend", "args": {"moods": ["wind_down_sleep"], "language": lang, "limit": 4}})
    out.append({"label": "fallback pair", "setup": no_sleep, "tool": "recommend", "args": {"moods": ["wind_down_sleep", "fresh_morning"], "limit": 3}})
    out.append({"label": "fallback single", "setup": no_sleep, "tool": "recommend", "args": {"moods": ["wind_down_sleep"]}})
    out.append({"label": "language miss no fallback", "tool": "recommend", "args": {"moods": ["sit_with_sadness"], "language": "Kannada"}})
    out.append({"label": "only one in language", "tool": "recommend", "args": {"moods": ["romantic_nostalgic"], "language": "Kannada"}})
    out.append({"label": "unknown mood", "tool": "recommend", "args": {"moods": ["hungry"]}})
    out.append({"label": "default limit", "tool": "recommend", "args": {"moods": ["joyful_celebrate"]}})
    return out


def normalise(tool, r):
    """Reduce a tool result to the facts both versions must agree on."""
    if r.get("error"):
        return {"error": r["error"]}
    if tool == "lookup_raaga":
        if not r["found"]:
            return {"found": False}
        x = r["raaga"]
        return {"found": True, "name": x["name"], "arohana": x["arohana"], "sources": x["sources"],
                "krithis": x["krithis_in_catalogue"]}
    if tool == "search_krithis":
        return {"found": r["found"], "krithis": [(k["title"], k["raaga"], k["tala"]) for k in r.get("krithis", [])],
                "similar": [s["title"] for s in r.get("similar_titles", [])]}
    if tool == "recommend":
        return {"moods": r["moods"], "language": r.get("language"), "empty_note": bool(r.get("note")) and not r["recommendations"],
                "note": r.get("note"), "closest": r.get("closest_match"),
                "why": [p["why"] for p in r["recommendations"]],
                "picks": [(p["raaga"], [k["title"] for k in p["krithis"]]) for p in r["recommendations"]]}
    if tool == "report_correction":
        return {"item": r.get("item"), "applied": r.get("applied_for_this_user")}
    return r


def run_python(cs, tmp_path):
    out = []
    for i, c in enumerate(cs):
        tb = Toolbox(CAT, ProfileStore(tmp_path / f"p{i}.db"), "parity")
        for name, args in c.get("setup", []):
            tb.run(name, args)
        out.append(tb.run(c["tool"], c["args"]))
    return out


def run_js(cs):
    payload = json.dumps({"html": build(write=False), "cases": cs})
    proc = subprocess.run(["node", str(ROOT / "tests" / "js_core_runner.js")], input=payload,
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_web_core_matches_python(tmp_path):
    cs = cases()
    py, js = run_python(cs, tmp_path), run_js(cs)
    assert len(py) == len(js) == len(cs)
    mismatches = []
    for c, p, j in zip(cs, py, js):
        np_, nj = normalise(c["tool"], p), normalise(c["tool"], j)
        if np_ != nj:
            mismatches.append(f"{c['label']}\n    python: {np_}\n    web:    {nj}")
    assert not mismatches, f"{len(mismatches)}/{len(cs)} cases differ:\n" + "\n".join(mismatches[:10])


def test_parity_covers_every_mood():
    assert {c["args"]["moods"][0] for c in cases() if c["tool"] == "recommend"} >= set(MOODS)
