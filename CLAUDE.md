# Carnatic Music Agent ("ManoRaga")

Guidance for Claude Code working in this repo.

## Product scope (v1)
1. Answer Carnatic music questions in simple language (adjusts to user level).
2. Recommend raagas/krithis from the user's mood or description of their day.
3. Learn user taste (likes/dislikes, languages, composers, level) and personalise.
Out of scope for v1: audio raaga identification (planned v2 as a separate service exposed as one tool).

## Architecture
- `data/*.csv` — curated knowledge base. **The source of truth for facts.** `verified=true` means the project
  owner (10 years of Carnatic training) reviewed the row: for raagas that covers scale, parent and foreign notes;
  mood tags are a separate judgement. Never flip `verified` yourself.
- Raaga `moods` are ordered (primary first) and are the single source of mood membership. `avoid_moods` is a hard
  exclusion; `Catalog.validate` rejects a raaga that is both tagged and avoided for the same mood.
- Every row has `sources` (semicolon-separated URLs). Reference sources, in order of trust for facts: Karnatik.com
  (scales, raagam/taalam/composer per song), Shivkumar.org (notation, taalam), Rasikas.org (expert discussion; use
  for disputed points and concert practice), Wikipedia (credible for raaga background and composers; song-level facts defer to
  Karnatik.com/Shivkumar.org). Sangeethapriya.org is an audio archive: good for listening links, not
  for text verification. When sources disagree, keep the reviewer's value and record the other view in `notes`.
- `alternate_parents` records genuine disagreements between schools. Present the primary parent and mention the
  alternate rather than picking a side.
- `carnatic/catalog.py` — loads + validates CSVs, fuzzy name matching (raaga spellings vary a lot).
- `carnatic/profile.py` — SQLite taste profile: explicit preferences + like/dislike feedback (latest wins).
- `carnatic/tools.py` — tool schemas + deterministic implementations. LLM interprets; tools retrieve and rank.
- `carnatic/agent.py` — tool-use loop over the Anthropic Messages API; system prompt rebuilt every round
  with the current profile.
- `evals/` — 40 live evals: tool, keyword, citation, saved-profile and LLM-rubric checks (multi-turn supported). `tests/` — offline unit tests.

## Rules
- `docs/agent-behaviour-rules.md` is the readable record of the owner's rules. Any change to a rule updates it in the
  same commit as the prompts, code, tests and evals.
- Catalogue changes (owner's rule): the agent only proposes. Corrections apply to that user at once and are queued;
  additions need trusted source URLs + quoted evidence and are queued. Approval is a curator action outside the model
  (`cli.py --curator` /approve, or `python -m carnatic.review`). Never give the agent an approve tool.
- Recommendations: a song is suggested only for moods it is tagged with (after the user's own notes); a raaga with no
  fitting song is not suggested; optional language filter. If NO song has the mood (any language), fall back one step to the
  mood's `fallback` list in data/moods.csv (owner-approved) and return closest_match; a language-only miss never falls back. Mirror any change in web/template.html (parity test).
- Scope policy (owner's rule): the agent only helps with Carnatic music, mood-based suggestions and the user's
  taste profile. Anything else is declined in 1-2 friendly sentences with a redirect. People in distress get care,
  never a refusal. Borderline-but-relevant questions (Hindustani counterparts, learning, occasions) are answered.
- Grounding policy (owner's rule): never state an assumption as a fact. Facts come from the catalogue, then a web
  search restricted to Karnatik.com / Shivkumar.org / Rasikas.org / Sangeethapriya.org / Wikipedia (Python agent: Anthropic
  web_search; web page: the viewer's Parallel Search connector, page tools web_search_trusted / web_fetch_trusted,
  which drop non-trusted domains in code and live outside the parity core), else the agent says it couldn't verify and gives source_links. Never guess.
- Moods of new songs (owner's rule): the agent infers them from what the trusted page says about the song (meaning,
  theme, rasa, when sung), suggests them with that basis, and the USER validates. propose_addition refuses an inferred
  mood without user_confirmed: true; moods in the user's own words need no confirmation.
- Updates are not new suggestions: a new song/raaga suggestion with the same title (ignoring "(Raaga)") and a compatible
  raaga as a PENDING one, or a correction of the same field on the same item, updates that one in place (new non-empty
  values win, nothing is erased; same id). Python: ProposalStore.propose_addition/_correction + merge_addition; page:
  mergeIntoBox in the core. tests/test_review_export.py replays a real 21 Nov sequence through both. An update after the
  curator decided reopens it in the Review panel (an added-to-catalogue one says to remove and re-add).
- Completeness (owner's rule): the agent searches the trusted sources for every missing field of a new song (raaga,
  composer, language, tala, form, meaning for the mood) on its own, before showing it; it asks the user only about
  fields those sources don't state. Page suggest_addition returns `missing` to prompt this.
- Background curator: `.claude/skills/curate-manoraga` (weekly scheduled task) + `carnatic/gaps.py` (deterministic gap
  ranking + growth towards catalogue_targets, room split by run_mix in curator/config.json; new raagas and their songs allowed) + `carnatic/curator.py` (check candidates; add to the page's suggestion box with
  the page's own twin/merge rule). Its moods carry needs_curator_confirmation; the owner's Accept confirms them (page
  merged()). The chat agent's propose_addition strips that marker. The curator never edits data/ or approves.
- Curation: one queue (proposals.db). The page's owner-only Review panel stores decisions in db `curation/decisions`
  and exports `manoraga-suggestions/1` JSON; carnatic/page_import.py imports it (accepted -> approved, rest queued,
  idempotent by page id). tests/test_review_export.py runs the page's export code against the importer: change both
  together. `ProposalStore.edit` corrects a pending proposal; curator-set moods carry source "curator".
- The page's "Add to catalogue" stores approved changes in db `catalog/overlay` (everyone reads, admin writes) and
  applies them on load over the built-in catalogue (checkChange/applyChange in the page core mirror
  ProposalStore validation and _apply; tests/test_review_export.py checks they give the same rows). Changes the repo
  already has are skipped, so overlay + rebuild is safe. The repo stays the source of truth: export + import.
- Never let the model state raaga/krithi facts from memory: add data or tools instead of prompt hacks.
- Any change to `data/` must keep `pytest` green (Catalog.validate catches dangling references).
- New tool => schema + `_t_<name>` method + unit test + at least one eval case.
- `web/index.html` is committed: friends publish it into their own Claude accounts (SETUP_IN_CLAUDE.md,
  .claude/skills/install-manoraga). After ANY change to `data/` or `web/template.html`, run `python scripts/build_web.py`
  and commit the result; tests/test_web_build.py fails if it is stale.
- The web page (`web/template.html`) re-implements the core in JavaScript between `/*@core-begin` and
  `/*@core-end*/`. `tests/test_parity.py` runs 225 identical tool calls through both and fails on any difference,
  so change ranking or matching logic in BOTH places. Keep those markers intact.
- Run `pytest -q` after every change; run `python -m evals.run_evals` after prompt or tool changes and
  report the pass rate per category before/after (compare files in evals/results/). Never weaken a case or a
  rubric to make it pass; fix the agent or the data.

## Domain glossary
- **Swarasthanas**: S, R1 R2 R3, G1 G2 G3, M1 M2, P, D1 D2 D3, N1 N2 N3 (R2=G1, R3=G2, D2=N1, D3=N2 share pitch).
- **Arohana / avarohana**: ascending / descending note sequence of a raaga.
- **Melakarta**: one of 72 parent scales with all 7 notes in order; numbered 1-72.
- **Janya**: raaga derived from a melakarta (may skip notes, be vakra/zig-zag, or use foreign notes = bhashanga).
- **Gamaka**: ornamentation/oscillation of a note; central to raaga identity — a raaga is not just a scale.
- **Krithi**: main composition form (pallavi, anupallavi, charanam). Trinity: Tyagaraja, Muthuswami Dikshitar,
  Syama Sastri.
- **Rasa**: the emotional flavour (e.g. karuna = compassion/pathos, shanta = peace, veera = valour,
  shringara = love/beauty, bhakti = devotion).
- Mood → raaga mappings are traditional associations, not universal truths; keep that framing in answers.

## Next steps
1. Grow the catalogue (target 150 raagas / 1,000 krithis) from reliable sources; add `source_url` column.
2. Get a knowledgeable musician to review rows and flip `verified`.
3. Add listen links (YouTube/Spotify search URLs) to recommendations.
4. Web UI (Streamlit or FastAPI + simple frontend) with thumbs up/down that calls record_feedback directly.
5. v2: `identify_raaga_from_swaras` (text, deterministic), then audio identification service.
