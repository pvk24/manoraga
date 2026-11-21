---
name: curate-manoraga
description: Run ManoRaga's background curator. Fill the catalogue's thin spots and grow it with well-known raagas and krithis it lacks, researched on the trusted Carnatic sites, each with suggested moods, and leave complete, checked suggestions in the owner's review queue. Use when a scheduled run or the user asks to run the curator, or to grow or fill gaps in the ManoRaga catalogue.
---

# ManoRaga background curator

You are the curator agent. You **research and suggest**. The owner reviews and approves in the chat page's Review panel. You never change `data/*.csv`, never commit, and never approve anything.

## Inputs
- **The repo** (github.com/pvk24/manoraga), cloned and up to date: `git pull`.
- **The owner's page:** the artifact slug, given in the request or the scheduled task's prompt. Its storage holds the suggestion box (`suggestions/<owner id>`) and the owner's review decisions (`curation/decisions`).

## Steps

1. **Find the work.** Run `python -m carnatic.gaps > /tmp/curator/gaps.json`. A run does two kinds of work:
   - **Gaps:** the `work_on` thin spots (moods, languages, raagas with too few songs), in order.
   - **Growth:** the `growth` section: well-known krithis the catalogue lacks (any mood) and well-known raagas it lacks, towards the catalogue targets.
   - After step 2, run `python -m carnatic.curator room --box /tmp/curator/box.json --decisions /tmp/curator/decisions.json`. It gives the `room` left in the owner's queue (at most `max_suggestions_per_run` curator suggestions wait at once; `add` enforces it) and its split into `slots`: `gaps`, `new_krithis`, `new_raagas`. If `room` is 0, stop and report that the queue is full: don't research.
   - Aim for the slots. If one kind has nothing solid, give its slots to the others; never exceed the room.
   - The file also lists every catalogue raaga and krithi title. Don't suggest anything already there.

2. **Read the review queue.** Use the artifact's database tools (db_whoami, db_get, db_list):
   - Get the owner's id with `db_whoami`.
   - Save the box document `suggestions/<owner id>` as `/tmp/curator/box.json` (`{"items": [...]}`; use `{"items": []}` if it doesn't exist). Note its version.
   - Save `curation/decisions` as `/tmp/curator/decisions.json` (`{"decisions": {...}}`).

   Songs already waiting there, or that the owner rejected, are off-limits. The checker enforces this.

3. **Research each gap on the trusted sites only.** Use Karnatik.com, Shivkumar.org, Rasikas.org, Sangeethapriya.org and Wikipedia. Wikipedia is good for raaga pages (scale, parent, character, compositions); for a song's raagam, taalam and composer prefer Karnatik.com or Shivkumar.org and note any disagreement in `details`. Use web search restricted to those domains (or Parallel Search with `site:` queries), and read the song pages themselves.
   - **Mood gap:** look for well-known songs whose meaning fits the mood. The gap's `hint_raagas` are a starting point, not a limit. Never use its `avoid_raagas`.
   - **Language gap:** look for well-known songs in that language.
   - **Raaga gap:** look for another well-known song in that raaga.
   - **New krithis (growth):** well-known concert krithis the catalogue lacks, in any mood: Trinity and other major composers' songs with a Karnatik.com or Shivkumar.org page first. Infer their moods from the meaning like any other song.
   - **New raagas (growth):** well-known raagas the catalogue lacks. Prefer raagas whose songs you found in this run but couldn't suggest (e.g. a lullaby in Harikambhoji), then raagas with many songs on Karnatik.com.
     - Fill `name`, `type` (melakarta or janya), `melakarta_number` (melakarta) or `parent` (janya: must be a catalogue raaga), `arohana` and `avarohana` in the catalogue's notation (S R1 R2 G2 ...), from the trusted page. Add `aliases` for other spellings on the page.
     - Moods: infer 1–2 from how the trusted page describes the raaga (character, rasa, the songs and occasions it's used for), `about: "raaga"`, marked `needs_curator_confirmation: true`. Never from memory: no description on a trusted page, no mood, so leave the raaga out.
     - Suggest a well-known song in the new raaga too when you can (it counts as a new krithi). The checker accepts a song whose raaga is suggested in the same run or is waiting for review, and puts the raaga first; the owner adds the raaga before its songs.
   - **Ragamalika songs:** give the raaga as `Ragamalika` (never suggest Ragamalika as a raaga) and list the song's raagas in `notes`, from the trusted page.
   - **A song in a raaga that's neither in the catalogue nor suggested** is refused. Suggest the raaga, or leave the song out and mention it in your report.
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

   A new raaga looks like this (list it before its songs):
   ```json
   {"type": "addition", "kind": "raaga", "name": "<raaga>",
    "record": {"name": "...", "aliases": "<other spellings>", "type": "janya", "parent": "<catalogue raaga>",
               "arohana": "S R2 G3 P D2 S", "avarohana": "S D2 P G3 R2 S", "moods": ["..."]},
    "sources": ["https://www.karnatik.com/..."],
    "evidence": "<the page's words for the scale and parent>",
    "mood_evidence": [{"mood": "...", "source": "<url>", "quote": "<verbatim line describing the raaga>",
                       "about": "raaga", "needs_curator_confirmation": true}],
    "details": "Growth: new raaga. <why it's worth adding; songs found in it>"}
   ```
   Start `details` with "Found for the gap: <label>." or "Growth: new krithi." / "Growth: new raaga." so the owner sees why it's there.

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
