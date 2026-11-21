"""Evals that test "not in the catalogue" behaviour must use songs that really aren't in it.
Importing a song can make such a case silently stale (Ninnu Kori, Bhajare Re Manasa on 21 Nov 2026)."""
import json
from pathlib import Path

from carnatic.catalog import Catalog

CASES = [json.loads(l) for l in (Path(__file__).resolve().parent.parent / "evals" / "cases.jsonl").read_text().splitlines() if l.strip()]


def test_absent_songs_are_still_absent():
    cat = Catalog.load()
    stale = [(c["id"], c["absent_from_catalogue"]) for c in CASES
             if c.get("absent_from_catalogue") and cat.krithis_for(title=c["absent_from_catalogue"])]
    assert not stale, f"these evals need a song that's still missing from the catalogue: {stale}"


def test_case_ids_are_unique():
    ids = [c["id"] for c in CASES]
    assert len(ids) == len(set(ids))
