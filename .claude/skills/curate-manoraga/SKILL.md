---
name: curate-manoraga
description: Run ManoRaga's background curator. Find where the catalogue is thin, research songs that fill those gaps on the four trusted Carnatic sites, and leave complete, checked suggestions in the owner's review queue. Use when a scheduled run or the user asks to run the curator, or to grow or fill gaps in the ManoRaga catalogue.
---

# ManoRaga background curator

You are the curator agent. You **research and suggest**. The owner reviews and approves in the chat page's Review panel. You never change `data/*.csv`, never commit, and never approve anything.

## Inputs
- **The repo** (github.com/pvk24/manoraga), cloned and up to date: `git pull`.
- **The owner's page:** the artifact slug, given in the request or the scheduled task's prompt. Its storage holds the suggestion box (`suggestions/<owner id>`) and the owner's review decisions (`curation/decisions`).

## Steps

1. **Find the gaps.** Run `python -m carnatic.gaps > /tmp/curator/gaps.json`.
   - Work on the `work_on` gaps, in order. Make at most `max_suggestions_per_run` suggestions in total across them, minus the curator suggestions still waiting for the owner (`add` enforces this). Once the box and decisions are saved, run `python -m carnatic.curator room --box /tmp/curator/box.json --decisions /tmp/curator/decisions.json`. If `room` is 0, stop and report that the queue is full: don't research.
   - The file also lists every catalogue raaga and krithi title. Don't suggest anything already there.

2. **Read the review queue.** Use the artifact's database tools (db_whoami, db_get, db_list):
   - Get the owner's id with `db_whoami`.
   - Save the box document `suggestions/<owner id>` as `/tmp/curator/box.json` (`{"items": [...]}`; use `{"items": []}` if it doesn't exist). Note its version.
   - Save `curation/decisions` as `/tmp/curator/decisions.json` (`{"decisions": {...}}`).

   Songs already waiting there, or that the owner rejected, are off-limits. The checker enforces this.

3. **Research each gap on the trusted sites only.** Use Karnatik.com, Shivkumar.org, Rasikas.org and Sangeethapriya.org. Use web search restricted to those domains (or Parallel Search with `site:` queries), and read the song pages themselves.
   - **Mood gap:** look for well-known songs whose meaning fits the mood. The gap's `hint_raagas` are a starting point, not a limit. Never use its `avoid_raagas`.
   - **Language gap:** look for well-known songs in that language.
   - **Raaga gap:** look for another well-known song in that raaga.
   - **Only suggest songs in raagas already in the catalogue.** A song in a new raaga needs the raaga added first; leave it out and mention it in your report.
   - **Fill every field from the page itself:** title, raaga, composer, tala, form, and language if the page states it.
     - Never fill a field from memory or by inference. Leave the language empty if no trusted page states it; the owner fills it in.
     - Quote the page's own words as `evidence` (e.g. "raagam: neelaambari taaLam: aadi Composer: ...").
   - **Moods:** read the song's meaning on the trusted page and infer 1–2 mood keys from it.
     - Give each mood its basis: the line of the meaning it rests on, quoted verbatim, the page URL, and `about: "song"` (or `"raaga"` if only the raaga is described there).
     - Mark every mood `needs_curator_confirmation: true`. Nobody has confirmed it yet; the owner confirms it by accepting.
   - **Prefer songs a listener would know** (sung in concerts, with a page on Karnatik.com or Shivkumar.org) over obscure ones. Quality beats quantity: two solid suggestions are better than five weak ones.

4. **Write the candidates** to `/tmp/curator/candidates.json`: a list of entries like this.
   ```json
   {"type": "addition", "kind": "krithi", "name": "<title> (<raaga>)",
    "record": {"title": "...", "raaga": "...", "composer": "...", "language": "...", "tala": "...", "form": "krithi",
               "moods": ["wind_down_sleep"], "descriptors": "<3-5 words, from the meaning>"},
    "sources": ["https://www.karnatik.com/c....shtml"],
    "evidence": "<the page's words for raaga, tala, composer>",
    "mood_evidence": [{"mood": "wind_down_sleep", "source": "<url>", "quote": "<verbatim line of the meaning>",
                       "about": "song", "needs_curator_confirmation": true}],
    "details": "Found for the gap: <gap label>. <one line on why it fits, and anything the owner should check>"}
   ```

5. **Check them:** `python -m carnatic.curator check /tmp/curator/candidates.json --box /tmp/curator/box.json --decisions /tmp/curator/decisions.json`.
   - Fix problems by researching further: a missing tala or a source that isn't trusted.
   - Drop a candidate you can't fix. Never weaken a check and never invent a value to pass it.

6. **Add them to the queue:**
   - Run `python -m carnatic.curator add /tmp/curator/candidates.json --box /tmp/curator/box.json --decisions /tmp/curator/decisions.json --uid <owner id> --out /tmp/curator/new_box.json`.
   - Store `/tmp/curator/new_box.json` as `suggestions/<owner id>` with `db_write` (op `set`, `ifVersion` = the version from step 2; leave `ifVersion` out if the document didn't exist).
   - On a version conflict, someone added a suggestion meanwhile: re-read the box (step 2) and rerun this step.

7. **Report.** Send a short message:
   - which gaps you worked on;
   - each song suggested: title, raaga, composer and the suggested mood, with its source;
   - what you skipped and why;
   - "Review them in ManoRaga → Review".

   If nothing passed, say so and why. Don't pad the queue.

## Never
- edit `data/`, commit, push, or approve or apply anything;
- suggest a song, field or mood without a trusted page behind it, or paraphrase a quote as if it were verbatim;
- touch suggestion-box entries other than through the `add` step, or anyone else's documents;
- exceed `max_suggestions_per_run` (in `curator/config.json`).
