"""Where the catalogue is thin: the work list for the background curator.

    python -m carnatic.gaps            # JSON: ranked gaps + what's already in the catalogue
    python -m carnatic.gaps --text     # the same, readable

Deterministic: counts songs per mood, per language and per raaga against the targets in curator/config.json and
ranks the shortfalls. Moods come first (they decide what people can be offered), then languages, then raagas with
too few songs. The curator agent picks the top few each run and researches songs to fill them.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

from .catalog import Catalog

CONFIG = Path(__file__).resolve().parent.parent / "curator" / "config.json"


def load_config(path: Path = CONFIG) -> dict:
    cfg = {"songs_per_mood": 6, "songs_per_language": 8, "songs_per_raaga": 2, "max_suggestions_per_run": 10,
           "max_gaps_per_run": 3, "skip_raagas": [], "catalogue_targets": {"raagas": 400, "krithis": 1000},
           "run_mix": {"gaps": 4, "new_krithis": 4, "new_raagas": 2}}
    if Path(path).exists():
        cfg.update({k: v for k, v in json.loads(Path(path).read_text(encoding="utf-8")).items() if not k.startswith("_")})
    return cfg


def find_gaps(cat: Catalog, cfg: dict | None = None) -> list[dict]:
    cfg = cfg or load_config()
    gaps = []
    by_mood = Counter(m for k in cat.krithis for m in k.moods)
    for key, mood in cat.moods.items():
        have = by_mood.get(key, 0)
        if have < cfg["songs_per_mood"]:
            raagas = [r.name for r in cat.raagas.values() if key in r.moods and key not in r.avoid_moods]
            gaps.append({"kind": "mood", "key": key, "label": mood.label, "have": have, "target": cfg["songs_per_mood"],
                         "brief": f"Songs that suit '{mood.label}' ({mood.when_to_use})",
                         "hint_raagas": raagas,
                         "avoid_raagas": [r.name for r in cat.raagas.values() if key in r.avoid_moods]})
    by_lang = Counter(k.language for k in cat.krithis if k.language)
    for lang in sorted(set(by_lang) | {"Tamil", "Kannada", "Telugu", "Sanskrit"}):
        have = by_lang.get(lang, 0)
        if have < cfg["songs_per_language"]:
            gaps.append({"kind": "language", "key": lang, "label": lang, "have": have, "target": cfg["songs_per_language"],
                         "brief": f"Well-known krithis in {lang}, in raagas already in the catalogue"})
    by_raaga = Counter(k.raaga for k in cat.krithis)
    for r in cat.raagas.values():
        if r.name in cfg["skip_raagas"]:
            continue
        have = by_raaga.get(r.name, 0)
        if have < cfg["songs_per_raaga"]:
            gaps.append({"kind": "raaga", "key": r.name, "label": r.name, "have": have, "target": cfg["songs_per_raaga"],
                         "brief": f"Another well-known song in {r.name}"})
    # Biggest relative shortfall first; within a kind, moods > languages > raagas.
    order = {"mood": 0, "language": 1, "raaga": 2}
    gaps.sort(key=lambda g: (order[g["kind"]], g["have"] / g["target"], g["key"]))
    return gaps


def plan(room: int, cfg: dict | None = None) -> dict:
    """Split this run's room across the kinds of work in the run_mix proportions (largest remainder).
    Slots a kind can't fill well may go to the others; the total never exceeds the room."""
    cfg = cfg or load_config()
    mix = {k: max(0, int(v)) for k, v in cfg["run_mix"].items()}
    total = sum(mix.values()) or 1
    raw = {k: room * v / total for k, v in mix.items()}
    slots = {k: int(v) for k, v in raw.items()}
    for k in sorted(raw, key=lambda k: (slots[k] - raw[k], list(mix).index(k)))[: room - sum(slots.values())]:
        slots[k] += 1
    return slots


def growth(cat: Catalog, cfg: dict | None = None) -> dict:
    """How far the catalogue is from its size targets."""
    cfg = cfg or load_config()
    t = cfg["catalogue_targets"]
    return {"raagas": {"have": len(cat.raagas), "target": t["raagas"],
                       "brief": "Well-known raagas the catalogue lacks (prefer ones whose songs you found but couldn't "
                                "suggest), with scale and parent from a trusted page and 1-2 moods from how the page "
                                "describes the raaga's character, rasa or use"},
            "krithis": {"have": len(cat.krithis), "target": t["krithis"],
                        "brief": "Well-known concert krithis the catalogue lacks, any mood, with 1-2 moods from the "
                                 "song's meaning"}}


def report(cat: Catalog | None = None, cfg: dict | None = None) -> dict:
    cat = cat or Catalog.load()
    cfg = cfg or load_config()
    gaps = find_gaps(cat, cfg)
    return {
        "targets": {k: cfg[k] for k in ("songs_per_mood", "songs_per_language", "songs_per_raaga")},
        "max_suggestions_per_run": cfg["max_suggestions_per_run"],
        "work_on": gaps[: cfg["max_gaps_per_run"]],
        "growth": growth(cat, cfg),
        "run_mix": cfg["run_mix"],
        "all_gaps": gaps,
        "catalogue": {"raagas": sorted(cat.raagas), "krithi_titles": sorted(k.title for k in cat.krithis)},
    }


def main(argv: list[str]) -> int:
    rep = report()
    if "--text" in argv:
        print(f"{len(rep['all_gaps'])} gaps. Work on now:")
        for g in rep["work_on"]:
            print(f"  [{g['kind']}] {g['label']}: {g['have']}/{g['target']} songs. {g['brief']}")
        for k, v in rep["growth"].items():
            print(f"  [grow] {k}: {v['have']}/{v['target']}. {v['brief']}")
        for g in rep["all_gaps"][len(rep["work_on"]):]:
            print(f"  later [{g['kind']}] {g['label']}: {g['have']}/{g['target']}")
    else:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
