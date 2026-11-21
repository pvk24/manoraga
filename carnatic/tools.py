"""Tools the agent can call. Deterministic: the LLM interprets, these retrieve and rank.

Each tool = a JSON schema (sent to Claude) + a Python function (run locally).
"""
from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote_plus

TRUSTED_SOURCES = ["karnatik.com", "shivkumar.org", "rasikas.org", "sangeethapriya.org", "wikipedia.org"]


def listen_links(title: str, raaga: str = "", composer: str = "") -> list[dict]:
    """Search links to hear a song (no specific recording is claimed). Must match listenLinks() in web/template.html.
    Only link types checked to open a results page (21 Nov 2026): YouTube search. Dropped: Sangeethapriya.org (no
    linkable search), Spotify (results could not be confirmed)."""
    words = " ".join(x for x in (title, raaga, "" if composer in ("", "unknown") else composer) if x)
    q = quote_plus(words.strip())
    return [
        {"site": "YouTube", "url": f"https://www.youtube.com/results?search_query={q}"},
    ]


def _with_listen(k: dict) -> dict:
    return {**k, "listen": listen_links(k["title"], k.get("raaga", ""), k.get("composer", ""))}


def source_links(query: str) -> list[dict]:
    """Search links on the trusted sources. Must match sourceLinks() in web/template.html (parity test).
    Only link types checked to open a results page (21 Nov 2026): a Google search naming the site (a site: search can
    come back empty) and Wikipedia's search. Rasikas.org's own search refuses visitors who aren't signed in."""
    q = quote_plus(query.strip())
    g = lambda site: f"https://www.google.com/search?q={site}+{q}"
    return [
        {"site": "Karnatik.com", "url": g("karnatik")},
        {"site": "Shivkumar.org", "url": g("shivkumar")},
        {"site": "Rasikas.org", "url": g("rasikas")},
        {"site": "Wikipedia", "url": f"https://en.wikipedia.org/w/index.php?search={q}"},
    ]

from .catalog import RAGAMALIKA, RAGAMALIKA_NOTE, Catalog, is_ragamalika
from .profile import ALLOWED_PREFS, ProfileStore
from .proposals import ProposalStore


class Toolbox:
    def __init__(self, catalog: Catalog, profiles: ProfileStore, user_id: str, proposals: ProposalStore | None = None):
        self.cat = catalog
        self.profiles = profiles
        self.proposals = proposals
        self.user_id = user_id
        self.calls: list[str] = []  # for evals / debugging

    # ---- schemas -------------------------------------------------------
    @property
    def schemas(self) -> list[dict]:
        mood_keys = list(self.cat.moods)
        return [
            {
                "name": "lookup_raaga",
                "description": "Get catalogue facts about a raaga: scale (arohana/avarohana), parent melakarta, mood tags, notes. "
                               "Use for ANY factual claim about a specific raaga. Handles spelling variants.",
                "input_schema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
            },
            {
                "name": "search_krithis",
                "description": "Find krithis (songs) in the catalogue by raaga, composer and/or title. "
                               "Use to answer 'which raaga is song X in', 'songs by Y', 'songs in raaga Z'.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "raaga": {"type": "string"},
                        "composer": {"type": "string"},
                        "title": {"type": "string"},
                    },
                },
            },
            {
                "name": "recommend",
                "description": "Recommend raagas and krithis for one or two moods, personalised to the user's taste profile. "
                               "First interpret what the user said (their day, feelings) into mood keys, then call this.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "moods": {"type": "array", "items": {"type": "string", "enum": mood_keys}, "minItems": 1, "maxItems": 2},
                        "language": {"type": "string", "description": "Only songs in this language, when the user asks for one (e.g. Kannada)"},
                        "limit": {"type": "integer", "default": 3, "minimum": 1, "maximum": 6},
                    },
                    "required": ["moods"],
                },
            },
            {
                "name": "record_feedback",
                "description": "Save a like or dislike the user expressed about a raaga, krithi or composer "
                               "(e.g. 'loved that one', 'Thodi is too heavy for me'). Call whenever taste is expressed.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "item_type": {"type": "string", "enum": ["raaga", "krithi", "composer"]},
                        "item_name": {"type": "string"},
                        "signal": {"type": "integer", "enum": [1, -1]},
                        "note": {"type": "string", "description": "Short reason in the user's words, if given"},
                    },
                    "required": ["item_type", "item_name", "signal"],
                },
            },
            {
                "name": "report_correction",
                "description": "The user says a catalogue song or raaga is described wrongly, e.g. 'that's not upbeat, it's "
                               "soothing' or 'that krithi is in Misra Chapu, not Adi'. This is NOT a dislike. Mood "
                               "corrections apply to this user's own suggestions at once AND are queued for the curator. "
                               "Factual corrections (raaga, composer, language, tala, scale) need a trusted source URL "
                               "and are only queued. Never say the catalogue is already changed.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "item_type": {"type": "string", "enum": ["krithi", "raaga"]},
                        "item_name": {"type": "string"},
                        "remove_moods": {"type": "array", "items": {"type": "string", "enum": mood_keys},
                                         "description": "Moods it should NOT be suggested for"},
                        "add_moods": {"type": "array", "items": {"type": "string", "enum": mood_keys},
                                      "description": "Moods it SHOULD count for, if the user says so"},
                        "field": {"type": "string", "enum": ["raaga", "composer", "language", "tala", "arohana",
                                                             "avarohana", "parent", "melakarta_number"],
                                  "description": "For a factual correction"},
                        "suggested_value": {"type": "string"},
                        "reason": {"type": "string", "description": "The user's words"},
                        "sources": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["item_type", "item_name", "reason"],
                },
            },
            {
                "name": "propose_addition",
                "description": "Propose adding a krithi or raaga you found and VERIFIED on a trusted source page "
                               "(Karnatik.com, Shivkumar.org, Rasikas.org, Sangeethapriya.org, Wikipedia). Use the source's values "
                               "only; never guess a field. The curator must approve before it enters the catalogue: "
                               "tell the user the proposal id. A krithi whose raaga is missing needs the raaga proposed first.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "kind": {"type": "string", "enum": ["krithi", "raaga"]},
                        "record": {"type": "object", "description":
                                   "krithi: title, raaga, composer, language (required), tala, form, moods (mood keys the "
                                   "user confirmed, with mood_evidence), descriptors. raaga: name, type (melakarta|janya), "
                                   "arohana, avarohana (required), melakarta_number, parent, moods, notes."},
                        "sources": {"type": "array", "items": {"type": "string"}, "description": "https URLs of the pages that state these facts"},
                        "evidence": {"type": "string", "description": "Short quote(s) from the source(s) showing each fact"},
                        "mood_evidence": {"type": "array", "description": "One entry per mood. source: a trusted URL whose "
                                          "text (meaning, rasa, when sung) you inferred the mood from, or 'user' for their own "
                                          "words; quote: that text; about: song or raaga; user_confirmed: true once the user "
                                          "has validated your suggested mood.",
                                          "items": {"type": "object", "properties": {
                                              "mood": {"type": "string"}, "source": {"type": "string"},
                                              "quote": {"type": "string"}, "about": {"type": "string", "enum": ["song", "raaga"]},
                                              "user_confirmed": {"type": "boolean"}},
                                              "required": ["mood", "source", "quote"]}},
                    },
                    "required": ["kind", "record", "sources", "evidence"],
                },
            },
            {
                "name": "source_links",
                "description": "Get search links for a raaga, krithi or question on the trusted sources (Karnatik.com, "
                               "Shivkumar.org, Rasikas.org, Sangeethapriya.org, Wikipedia). Use when you cannot verify a fact, "
                               "so the user can check it themselves.",
                "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
            },
            {
                "name": "listen_links",
                "description": "Get a link to listen to a song: a YouTube search for its title, raaga and composer (searches, not a specific recording). Use as soon as the user wants to hear a song, including songs found on the trusted sites that are not in the catalogue. Catalogue songs from recommend/search_krithis already carry these as `listen`.",
                "input_schema": {"type": "object", "properties": {
                    "title": {"type": "string"}, "raaga": {"type": "string"}, "composer": {"type": "string"}},
                    "required": ["title"]},
            },
            {
                "name": "set_preference",
                "description": "Save an explicit user setting. Allowed keys: " + json.dumps(ALLOWED_PREFS),
                "input_schema": {
                    "type": "object",
                    "properties": {"key": {"type": "string", "enum": list(ALLOWED_PREFS)}, "value": {}},
                    "required": ["key", "value"],
                },
            },
        ]

    # ---- dispatch ------------------------------------------------------
    def run(self, name: str, args: dict[str, Any]) -> Any:
        self.calls.append(name)
        fn = getattr(self, f"_t_{name}", None)
        if not fn:
            return {"error": f"unknown tool {name}"}
        try:
            return fn(**args)
        except TypeError as e:
            return {"error": f"bad arguments: {e}"}

    # ---- implementations ----------------------------------------------
    def _t_lookup_raaga(self, name: str):
        r = self.cat.resolve_raaga(name)
        if not r and is_ragamalika(name):
            return {"found": False, "ragamalika": True, "message": RAGAMALIKA_NOTE,
                    "krithis_in_catalogue": [k.title for k in self.cat.krithis_for(raaga=RAGAMALIKA)]}
        if not r:
            return {"found": False, "message": f"'{name}' is not in the catalogue."}
        d = r.to_dict()
        d["krithis_in_catalogue"] = [k.title for k in self.cat.krithis_for(raaga=r.name)]
        return {"found": True, "raaga": d}

    def _t_search_krithis(self, raaga: str | None = None, composer: str | None = None, title: str | None = None):
        if not any([raaga, composer, title]):
            return {"error": "provide at least one of raaga, composer, title"}
        res = self.cat.krithis_for(raaga=raaga, composer=composer, title=title)
        out = {"found": True, "krithis": [_with_listen(k.to_dict()) for k in res[:15]]} if res else \
              {"found": False, "message": "No matching krithis in the catalogue."}
        if title:
            sim = self.cat.similar_titles(title, exclude={k.title for k in res})
            if sim:
                out["similar_titles"] = sim   # look-alike titles: a common source of mix-ups
        return out

    def _t_recommend(self, moods: list[str], limit: int = 3, language: str | None = None):
        """Recommend for the requested moods. If no song in the catalogue is tagged with them (in any language),
        fall back to each mood's closest moods (data/moods.csv `fallback`, one step, in order) and label it.
        A language miss does NOT fall back: the mood matters more than the language (owner's rule)."""
        moods = [m for m in moods if m in self.cat.moods]
        if not moods:
            return {"error": "unknown mood keys", "valid": list(self.cat.moods)}
        lang = (language or "").strip().lower()
        out = self._rank(moods, set(), limit, lang)
        res = {"moods": moods, "recommendations": out}
        if lang:
            res["language"] = language
        if out:
            if lang and len(out) < limit:
                res["note"] = f"Only {len(out)} fitting pick(s) in {language}. Say so plainly; don't add other moods."
            return res
        if lang and self._rank(moods, set(), limit, ""):
            res["note"] = (f"No song in the catalogue fits this mood in {language}, though some do in other languages. "
                           "Say so and offer those; don't swap in another mood.")
            return res
        tried = set(moods)
        for i in (0, 1):
            for m in moods:
                fb = self.cat.moods[m].fallback
                if i >= len(fb) or fb[i] in tried:
                    continue
                tried.add(fb[i])
                alt = self._rank([fb[i]], set(moods), limit, lang)
                if alt:
                    asked = " / ".join(f"'{self.cat.moods[x].label}'" for x in moods)
                    res["recommendations"] = alt
                    res["closest_match"] = {"used_mood": fb[i], "label": self.cat.moods[fb[i]].label,
                        "note": f"No catalogue song is tagged {asked}. These are tagged '{self.cat.moods[fb[i]].label}', "
                                "the closest mood. Tell the user that plainly before the picks."}
                    return res
        res["note"] = ("No song in the catalogue fits this mood" + (f" in {language}" if lang else "") +
                       ". Say so; don't stretch other songs to fit.")
        return res

    def _rank(self, moods: list[str], guard: set, limit: int, lang: str):
        """Core ranking. `guard`: the originally requested moods when ranking a fallback mood; raagas and songs
        that avoid any of them are excluded."""
        """Rules (mirrored exactly in web/template.html; tests/test_parity.py checks):
        - a raaga qualifies through its own mood tags, or through a song tagged with the mood;
        - a SONG is suggested only if it is tagged for one of the requested moods (after the user's overrides);
          a raaga with no fitting song is not suggested;
        - optional language filter on songs; user overrides ("not upbeat for me") act as personal avoid rules."""
        prof = self.profiles.get(self.user_id)
        ov = prof.get("mood_overrides", {})

        def eff(kind: str, name: str, base: list[str], avoid: list[str]):
            o = ov.get(f"{kind}|{name.lower()}")
            if not o:
                return list(base), list(avoid)
            tags = [m for m in base if m not in o["remove"]] + [m for m in o["add"] if m not in base]
            return tags, list(avoid) + [m for m in o["remove"] if m not in avoid]

        liked_r = {x.lower() for x in prof["likes"]["raaga"]}
        disliked_r = {x.lower() for x in prof["dislikes"]["raaga"]}
        as_list = lambda v: [v] if isinstance(v, str) else list(v or [])  # the agent may send "Tamil" or ["Tamil"]
        liked_c = {x.lower() for x in prof["likes"]["composer"] + as_list(prof["preferences"].get("favourite_composers"))}
        disliked_c = {x.lower() for x in prof["dislikes"]["composer"]}
        disliked_k = {x.lower() for x in prof["dislikes"]["krithi"]}
        liked_k = {x.lower() for x in prof["likes"]["krithi"]}
        langs = {x.lower() for x in as_list(prof["preferences"].get("languages"))}
        R = {name: eff("raaga", name, r.moods, r.avoid_moods) for name, r in self.cat.raagas.items()}
        R[RAGAMALIKA] = ([], [])        # not a raaga: its songs qualify it, and it has no tags of its own
        K = {k.title: eff("krithi", k.title, k.moods, k.avoid_moods) for k in self.cat.krithis}

        # Score raagas: primary mood tag scores highest, then secondary, then the rest.
        rank_score = {0: 3.0, 1: 2.0}
        scores: dict[str, float] = {}
        reasons: dict[str, list[str]] = {}
        for m in moods:
            for name in self.cat.raagas:
                tags, avoid = R[name]
                if m in tags and m not in avoid:
                    rank = tags.index(m)
                    scores[name] = scores.get(name, 0) + rank_score.get(rank, 1.0)
                    kind = "primary" if rank == 0 else "secondary" if rank == 1 else "also"
                    reasons.setdefault(name, []).append(f"{kind} fit for '{self.cat.moods[m].label}'")
        # A raaga can also qualify through a song tagged with the mood (e.g. Paramapurusha makes Vasantha energetic).
        # Already tagged: the song only breaks ties (+0.5). Not tagged: the song qualifies it (primary 2, else 1).
        song_bonus: dict[str, tuple[float, str]] = {}
        for m in moods:
            for k in self.cat.krithis:
                ktags, kavoid = K[k.title]
                rtags, ravoid = R[k.raaga]
                if m in ktags and m not in kavoid and m not in ravoid:
                    b = 0.5 if m in rtags else (2.0 if ktags.index(m) == 0 else 1.0)
                    if b > song_bonus.get(k.raaga, (0, ""))[0]:
                        song_bonus[k.raaga] = (b, f"song '{k.title}' fits '{self.cat.moods[m].label}'")
        for r, (b, why) in song_bonus.items():
            scores[r] = scores.get(r, 0) + b
            reasons.setdefault(r, []).append(why)
        for r in list(scores):
            if guard & set(R[r][0]):   # fallback: raagas that themselves suit the requested mood come first
                scores[r] += 3; reasons[r].append("raaga itself suits '" + "/".join(self.cat.moods[g].label for g in sorted(guard & set(R[r][0]))) + "'")
            if r.lower() in liked_r:
                scores[r] += 2; reasons[r].append("you liked this raaga before")
            if r.lower() in disliked_r:
                scores[r] -= 5; reasons[r].append("you disliked this raaga (deprioritised)")

        order = {name: i for i, name in enumerate(self.cat.raagas)}
        order[RAGAMALIKA] = len(order)
        ranked = sorted(scores, key=lambda r: (-scores[r], order[r]))  # ties: catalogue order (same as the page)
        out = []
        for r in ranked:
            if scores[r] <= 0 or guard & set(R[r][1]):
                continue
            ks = []
            for k in self.cat.krithis:
                if k.raaga != r:
                    continue
                if k.title.lower() in disliked_k or (k.composer and k.composer.lower() in disliked_c):
                    continue
                ktags, kavoid = K[k.title]
                if (set(moods) | guard) & set(kavoid):
                    continue
                if not set(moods) & set(ktags):      # the song itself must fit the mood
                    continue
                if lang and k.language.lower() != lang:
                    continue
                s = 0.0
                for m in moods:
                    if m in ktags:
                        s += 3 if ktags.index(m) == 0 else 2
                if k.composer and any(c in k.composer.lower() for c in liked_c): s += 1
                if langs and k.language.lower() in langs: s += 0.5
                if k.title.lower() in liked_k: s -= 0.5  # nudge towards discovery, keep it if nothing else
                ks.append((s, k))
            if not ks:                                # no fitting song: don't suggest the raaga
                continue
            ks.sort(key=lambda x: x[0], reverse=True)
            out.append({
                "raaga": r,
                "why": reasons[r],
                "raaga_notes": self.cat.raagas[r].notes if r in self.cat.raagas else RAGAMALIKA_NOTE,
                "krithis": [{"title": k.title, "composer": k.composer or "unknown", "language": k.language,
                             "character": k.descriptors, "listen": listen_links(k.title, k.raaga, k.composer)}
                            for _, k in ks[:2]],
            })
            if len(out) >= limit:
                break
        return out

    def _t_record_feedback(self, item_type: str, item_name: str, signal: int, note: str = ""):
        return self.profiles.record_feedback(self.user_id, item_type, item_name, signal, note)

    def _t_report_correction(self, item_type: str, item_name: str, reason: str, remove_moods: list | None = None,
                             add_moods: list | None = None, field: str | None = None, suggested_value=None,
                             sources: list | None = None):
        """Mood part must match reportCorrection() in web/template.html (parity test)."""
        if item_type == "krithi":
            hit = next((k for k in self.cat.krithis if k.title.lower() == item_name.strip().lower()), None)
            name = hit.title if hit else None
        else:
            r = self.cat.resolve_raaga(item_name)
            name = r.name if r else None
        if not name:
            return {"error": f"'{item_name}' is not in the catalogue"}
        remove_moods = [m for m in remove_moods or [] if m in self.cat.moods]
        add_moods = [m for m in add_moods or [] if m in self.cat.moods]
        out: dict = {"item": name}
        if remove_moods or add_moods:
            self.profiles.set_mood_override(self.user_id, item_type, name, remove_moods, add_moods)
            out["applied_for_this_user"] = {"remove": remove_moods, "add": add_moods}
            if self.proposals:
                out["proposal"] = self.proposals.propose_correction(
                    self.user_id, self.cat, item_type, name, "moods",
                    {"remove": remove_moods, "add": add_moods}, reason, sources)
        if field:
            if not self.proposals:
                out["proposal"] = {"error": "corrections can't be queued here"}
            else:
                out["fact_proposal"] = self.proposals.propose_correction(
                    self.user_id, self.cat, item_type, name, field, suggested_value, reason, sources)
        if len(out) == 1:
            return {"error": "give remove_moods/add_moods, or field + suggested_value"}
        out["note"] = "The shared catalogue changes only after the curator approves."
        return out

    def _t_propose_addition(self, kind: str, record: dict, sources: list, evidence: str, mood_evidence: list | None = None):
        if not self.proposals:
            return {"error": "additions can't be proposed in this app"}
        # The chat agent must get the user's confirmation for an inferred mood; it can't defer it to the curator
        # (only the background curator's entries, arriving through the review import, carry that marker).
        mev = [{k: v for k, v in e.items() if k != "needs_curator_confirmation"} if isinstance(e, dict) else e
               for e in mood_evidence or []]
        return self.proposals.propose_addition(self.user_id, self.cat, kind, dict(record), sources, evidence, mev)

    def _t_source_links(self, query: str):
        return {"query": query, "links": source_links(query)}

    def _t_listen_links(self, title: str, raaga: str = "", composer: str = ""):
        return {"title": title, "links": listen_links(title, raaga or "", composer or ""),
                "note": "Search pages, not a specific recording: say so in one short clause."}

    def _t_set_preference(self, key: str, value):
        return self.profiles.set_preference(self.user_id, key, value)
