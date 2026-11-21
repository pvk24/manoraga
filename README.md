# ManoRaga: a Carnatic music agent

New here? Start with the one-page [overview](docs/overview.md): why ManoRaga exists, what it does and how it works.

Ask about Carnatic music in plain language, get raaga and krithi suggestions for your mood, and let it learn your taste.

## Quick start
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # add your ANTHROPIC_API_KEY
pytest -q                       # offline tests, no key needed
python seed_profile.py --user pranav   # preload your favourite krithis as likes
python cli.py --user pranav --debug
python -m evals.run_evals       # 40 live evals (uses API credits); results saved to evals/results/
python -m evals.run_evals --only ground   # just one category
```

## Use it yourself (for friends)
**Recommended: in your own Claude account, with the same chat page.** Follow [SETUP_IN_CLAUDE.md](SETUP_IN_CLAUDE.md):
attach `web/index.html` in a claude.ai chat and paste one message. It runs on your own Claude subscription (no API
key, no cost to anyone else), with the same chat, song cards, taste panel and web search of the trusted sources.

**Or in a terminal, with an API key.** You need Python 3.10+, git, and your own Anthropic API key (console.anthropic.com → API keys; this is
pay-as-you-go and separate from a Claude.ai subscription). Your chats are billed to your key.

```bash
git clone https://github.com/pvk24/manoraga.git && cd manoraga
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                   # Windows: copy .env.example .env
# open .env and paste your key after ANTHROPIC_API_KEY=
python cli.py --user yourname
```
- Your taste profile is saved on your machine (`user_data.db`), never uploaded.
- Web search of the four trusted sites is on by default (`CARNATIC_WEB_SEARCH=1`). It is enabled for API accounts
  unless an admin turned it off, and costs $10 per 1,000 searches plus tokens. Set it to 0 for catalogue-only answers.
- Songs the agent proposes go to *your* local queue: `python cli.py --user yourname --curator`, then `/proposals`.
  Approving them changes only your copy. To suggest a change to the shared catalogue, open a GitHub issue or pull
  request with the source link.
- Get updates with `git pull`. If it fails because you approved local changes, `git stash` first.

## Try
- "What's the difference between a raaga and a scale?"
- "Which raaga is Nagumomu in?"
- "Long day, feeling a bit low. Something comforting?"
- "I'm a beginner and prefer Tamil songs." then "Thodi is too heavy for me."

## How it works
The rules the agent follows (scope, grounding, recommendations, corrections, data policy) are written up in
[docs/agent-behaviour-rules.md](docs/agent-behaviour-rules.md).

The LLM interprets (your mood, your question, your level) and decides which tool to call. Tools are deterministic:
they look up the curated catalogue in `data/` and rank by your taste profile. Facts come from the data, not
from the model's memory. See `CLAUDE.md` for architecture and conventions.

## Data status
Catalogue: 41 raagas, 70 krithis (all with tala and mood tags), 12 moods. All rows expert-reviewed
(`verified=true`) except the Ragamalika placeholder row. Everything else is still a draft. Mood tags are ordered primary-first;
`avoid_moods` lists moods a raaga must never be recommended for.

Krithis carry their own ordered mood tags and `descriptors` (the reviewer's words, verbatim), because a song can
differ from its raaga's general character (Vallinayakane is devotional but not energetic, even in Shanmukhapriya).

## Web chat UI
`web/template.html` is a hosted chat page that runs the same agent in the browser: Claude is called from the page
with the tools (catalogue lookups, recommend, feedback) ported to JavaScript, and the taste profile is saved
privately per signed-in viewer. Rebuild after any data change, then republish:
```bash
python scripts/build_web.py     # writes web/index.html with the CSV catalogue embedded
```
The JS port must match `carnatic/`: `pytest` includes a parity test (needs Node.js) that runs 225 identical
tool calls through both versions and fails on any difference.

## Corrections and new songs (curator flow)
The agent can only **propose** catalogue changes; you approve them.

- **Corrections** ("that's not upbeat, it's soothing"): applied to that user's suggestions at once, and queued for you.
- **New songs/raagas** (Python agent): found by web search on Karnatik.com / Shivkumar.org / Rasikas.org /
  Sangeethapriya.org, proposed with source URLs and quoted evidence, and queued for you. The agent also infers moods from
  the song's meaning on those pages and suggests them; the user confirms before they're proposed.
- **Updates, not duplicates:** when a user adds to or corrects a song that's already waiting for review, the same
  suggestion is updated (and reopened for review if you had decided). The agent looks up missing facts itself.
- **Review in the terminal:** `python cli.py --curator` then `/proposals`, `/edit <id> field=value ...`
  (e.g. `/edit 3 tala="Misra Chapu" moods="calm_anxious;comfort_when_low" note="per Karnatik.com"`),
  `/approve <id>`, `/reject <id> <reason>`; or the same as `python -m carnatic.review list|show|edit|approve|reject`.
  Approving writes `data/*.csv` (new rows have `verified=false`, their sources, where each mood came from and any
  edits you made), re-validates the catalogue, and rolls back if anything is inconsistent.
- **Review in the chat page:** the page's owner gets a **Review** button (with a count) in the header. Each
  suggestion shows its facts, sources, evidence and the basis for each mood; Accept, Edit or Reject it there.
  **Add to catalogue** (one, or all accepted) puts them live in the page straight away, checked by the same rules
  as the repo, and **Remove from catalogue** takes one back out. These live changes are stored in the page, not the
  repo, so the panel shows how many are "not in your repo yet".
  To update the CSVs too, **Export for the repo** and import the file: `python -m carnatic.review import manoraga-suggestions.json`
  (or `/import` in the curator chat). Accepted and already-added ones are applied; undecided ones join the same queue
  as the terminal agent's proposals; re-importing a file is safe. Or ask Claude to "import the ManoRaga suggestion box".
- After approving, rebuild and republish the page: `python scripts/build_web.py`.
