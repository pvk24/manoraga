"""Curated knowledge base: raagas, krithis, moods. Loaded from CSVs in data/.

Small enough to keep in memory. Move to SQLite/Postgres once it passes ~5k krithis.
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _norm(s: str) -> str:
    """Normalise names for matching: lowercase, strip spaces/punctuation, fold common spelling variants."""
    s = s.lower()
    s = re.sub(r"[^a-z]", "", s)
    for a, b in (("dh", "d"), ("th", "t"), ("bh", "b"), ("kh", "k"), ("sh", "s"), ("aa", "a"), ("ee", "i"), ("oo", "u"), ("v", "w")):
        s = s.replace(a, b)
    return s


def _lev(a: str, b: str) -> int:
    d = list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        prev, d[0] = d[0], i
        for j in range(1, len(b) + 1):
            t = d[j]
            d[j] = min(d[j] + 1, d[j - 1] + 1, prev + (a[i - 1] != b[j - 1]))
            prev = t
    return d[len(b)]


def _ratio(a: str, b: str) -> float:
    """Similarity 0..1. Must match ratio() in web/template.html (tests/test_parity.py checks)."""
    m = max(len(a), len(b))
    return 1 - _lev(a, b) / m if m else 1.0


def _split(s: str) -> list[str]:
    return [x.strip() for x in (s or "").split(";") if x.strip()]


UPLIFTING = {"comfort_when_low", "joyful_celebrate", "energise_motivate", "light_playful", "grand_uplifted"}


@dataclass
class Raaga:
    name: str
    aliases: list[str]
    type: str
    melakarta_number: int | None
    parent: str
    alternate_parents: list[str]
    arohana: str
    avarohana: str
    scale_note: str
    foreign_notes: list[str]
    moods: list[str]          # ordered: primary first, then secondary
    avoid_moods: list[str]    # never recommend this raaga for these moods
    rasa: list[str]
    time_of_day: str
    notes: str
    sources: list[str]
    verified: bool

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        if not self.verified:
            d["caveat"] = "Scale/parent not yet expert-verified."
        return d


@dataclass
class Krithi:
    title: str
    raaga: str
    composer: str
    language: str
    tala: str
    form: str
    moods: list[str]          # song-level tags, ordered primary first (can differ from the raaga's)
    avoid_moods: list[str]
    descriptors: str          # reviewer's own words, kept verbatim
    notes: str
    sources: list[str]        # where the facts were checked (Karnatik.com, Shivkumar.org, Rasikas.org)
    verified: bool

    def to_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class Mood:
    key: str
    label: str
    when_to_use: str
    fallback: list[str] = field(default_factory=list)  # closest moods, in order; used only when no song fits the mood


@dataclass
class Catalog:
    raagas: dict[str, Raaga] = field(default_factory=dict)
    krithis: list[Krithi] = field(default_factory=list)
    moods: dict[str, Mood] = field(default_factory=dict)
    _index: dict[str, str] = field(default_factory=dict)  # normalised name/alias -> canonical name

    @classmethod
    def load(cls, data_dir: Path = DATA_DIR) -> "Catalog":
        cat = cls()
        with open(data_dir / "raagas.csv", newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                raaga = Raaga(
                    name=r["name"],
                    aliases=_split(r["aliases"]),
                    type=r["type"],
                    melakarta_number=int(r["melakarta_number"]) if r["melakarta_number"] else None,
                    parent=r["parent"],
                    alternate_parents=_split(r["alternate_parents"]),
                    arohana=r["arohana"],
                    avarohana=r["avarohana"],
                    scale_note=r["scale_note"],
                    foreign_notes=_split(r["foreign_notes"]),
                    moods=_split(r["moods"]),
                    avoid_moods=_split(r["avoid_moods"]),
                    rasa=_split(r["rasa"]),
                    time_of_day=r["time_of_day"],
                    notes=r["notes"],
                    sources=_split(r.get("sources", "")),
                    verified=r["verified"].lower() == "true",
                )
                cat.raagas[raaga.name] = raaga
                cat._index[_norm(raaga.name)] = raaga.name
                for a in raaga.aliases:
                    k = _norm(re.sub(r"\(.*?\)", "", a))
                    if k:
                        cat._index.setdefault(k, raaga.name)
        with open(data_dir / "krithis.csv", newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                cat.krithis.append(Krithi(
                    title=r["title"], raaga=r["raaga"], composer=r["composer"], language=r["language"],
                    tala=r["tala"], form=r["form"], moods=_split(r.get("moods", "")),
                    avoid_moods=_split(r.get("avoid_moods", "")), descriptors=r.get("descriptors", ""), notes=r.get("notes", ""),
                    sources=_split(r.get("sources", "")), verified=r["verified"].lower() == "true",
                ))
        with open(data_dir / "moods.csv", newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                cat.moods[r["mood_key"]] = Mood(r["mood_key"], r["label"], r["when_to_use"], _split(r.get("fallback", "")))
        cat.validate()
        return cat

    def validate(self) -> None:
        """Fail fast on dangling references so bad data never reaches the agent."""
        errors = []
        for k in self.krithis:
            if k.raaga not in self.raagas:
                errors.append(f"krithi '{k.title}' references unknown raaga '{k.raaga}'")
        for k in self.krithis:
            for m in k.moods + k.avoid_moods:
                if m not in self.moods:
                    errors.append(f"krithi '{k.title}' references unknown mood '{m}'")
            if set(k.moods) & set(k.avoid_moods):
                errors.append(f"krithi '{k.title}' is both tagged and avoided for the same mood")
            if k.raaga in self.raagas and set(k.moods) & set(self.raagas[k.raaga].avoid_moods):
                errors.append(f"krithi '{k.title}' is tagged with a mood its raaga '{k.raaga}' avoids — resolve explicitly")
        for r in self.raagas.values():
            for m in r.moods + r.avoid_moods:
                if m not in self.moods:
                    errors.append(f"raaga '{r.name}' references unknown mood '{m}'")
            clash = set(r.moods) & set(r.avoid_moods)
            if clash:
                errors.append(f"raaga '{r.name}' is both tagged and avoided for {sorted(clash)}")
        for mo in self.moods.values():
            for m in mo.fallback:
                if m not in self.moods or m == mo.key:
                    errors.append(f"mood '{mo.key}' has an invalid fallback '{m}'")
            # Owner's rule: someone who wants to sit with sadness is never cheered up by a fallback.
            if mo.key == "sit_with_sadness" and set(mo.fallback) & UPLIFTING:
                errors.append("sit_with_sadness must not fall back to an uplifting mood")
        if errors:
            raise ValueError("Catalogue errors:\n" + "\n".join(errors))

    # ---- lookups -------------------------------------------------------
    def raagas_for_mood(self, mood: str) -> list[tuple[Raaga, int]]:
        """Raagas tagged with a mood, with rank (0 = primary mood, 1 = secondary, ...). Avoided raagas excluded."""
        out = [(r, r.moods.index(mood)) for r in self.raagas.values()
               if mood in r.moods and mood not in r.avoid_moods]
        return sorted(out, key=lambda x: x[1])

    def resolve_raaga(self, name: str) -> Raaga | None:
        key = _norm(name)
        if key in self._index:
            return self.raagas[self._index[key]]
        best, bs = None, 0.0
        for k in self._index:  # first strictly-best match wins, same as the page
            r = _ratio(key, k)
            if r > bs:
                best, bs = k, r
        return self.raagas[self._index[best]] if bs >= 0.8 else None

    def similar_titles(self, title: str, exclude: set[str] | None = None) -> list[dict]:
        """Catalogue krithis whose titles look like `title` (same opening word, or close spelling).
        Must match similarTitles() in web/template.html (parity test)."""
        t = _norm(title)
        first = _norm(title.split()[0]) if title.split() else ""
        out = []
        for k in self.krithis:
            if exclude and k.title in exclude:
                continue
            kn = _norm(k.title)
            kfirst = _norm(k.title.split()[0])
            if (len(first) >= 4 and kfirst == first) or _ratio(t, kn) >= 0.7:
                out.append({"title": k.title, "raaga": k.raaga, "composer": k.composer})
        return out[:5]

    def krithis_for(self, raaga: str | None = None, composer: str | None = None, title: str | None = None) -> list[Krithi]:
        out = self.krithis
        if raaga:
            r = self.resolve_raaga(raaga)
            if not r:
                return []
            out = [k for k in out if k.raaga == r.name]
        if composer:
            c = _norm(composer)
            out = [k for k in out if c in _norm(k.composer)]
        if title:
            t = _norm(title)
            exact = [k for k in out if t in _norm(k.title)]
            if exact:
                out = exact
            else:
                scored = [(_ratio(t, _norm(k.title)), k) for k in out]
                scored = [x for x in scored if x[0] >= 0.75]
                scored.sort(key=lambda x: -x[0])  # stable, same as the page
                out = [k for _, k in scored[:3]]
        return out
