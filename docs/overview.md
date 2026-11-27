# ManoRaga: overview

ManoRaga is a Carnatic music companion. It explains the music in plain words, suggests raagas and krithis for how you feel, and learns what you like. It never makes up a fact.

## Why

- **Carnatic music is hard to get into.** Raaga names have many spellings, facts are scattered across sites, and a beginner can't tell a raaga from a scale.
- **General chatbots sound sure and are often wrong.** They put songs in the wrong raaga or tala. In this music that is worse than no answer.
- **People choose music by mood, but music apps don't capture the tradition.** Which raaga suits a low evening or a fresh morning is knowledge held by teachers and listeners.
- **A trustworthy guide needs a human curator.** ManoRaga is built and curated by a listener with ten years of Carnatic training. Every fact is traceable to a source.

## What

| It does | In practice |
|---|---|
| Answers questions | Raagas, krithis, composers, concepts. It matches your level (beginner to advanced) and uses everyday analogies. |
| Suggests music for your mood or day | Maps "long day, feeling low" to one of 17 moods, then picks raagas with a song that fits, with a reason for each. It can filter by language. If nothing fits, it offers the closest mood and says so. |
| Learns your taste | Remembers likes, dislikes, languages, favourite composers and your own notes ("that song isn't upbeat for me"). Later suggestions change accordingly. |
| Grows its catalogue with you | Finds missing songs on trusted sites and fills in every detail. It suggests a mood from the song's meaning, which you confirm. The owner approves before anything is added. |
| Curates in the background | Once a week, a curator agent finds where the catalogue is thin (moods, languages, raagas), researches songs to fill the gaps and leaves checked suggestions for the owner to review. |
| Stays in its lane | Declines anything outside Carnatic music in a sentence or two. People in distress get care first. |

**Today:** 42 raagas, 82 krithis, 21 composers, 4 languages (Telugu, Sanskrit, Tamil, Kannada) and 17 moods. Every entry cites its sources, and every row is owner-reviewed.

**Two ways to use it:**
1. The **chat page**, published into your own Claude account. It runs on your Claude subscription and needs no API key. See [SETUP_IN_CLAUDE.md](../SETUP_IN_CLAUDE.md).
2. The **terminal agent**, which needs an Anthropic API key. See the [README](../README.md).

## How

**The model interprets; tools decide.** Claude reads your message and chooses a tool. The tools are plain code: they look up the curated catalogue (`data/*.csv`) and rank results against your taste profile. Facts come from data, not from the model's memory.

**Where facts come from, in order:**
1. the catalogue;
2. a web search limited to Karnatik.com, Shivkumar.org, Rasikas.org, Sangeethapriya.org and Wikipedia (results from any other site are dropped in code);
3. otherwise "I couldn't verify this", with links to check.

**How a suggestion is made:**
1. Your words are mapped to a mood.
2. Raagas tagged with that mood are scored.
3. A raaga is only offered if one of its songs is itself tagged for that mood.
4. The ranking takes into account your likes and dislikes, preferred languages and composers, and your own notes on songs.
5. If no song fits, the agent falls back one step along an owner-approved map of closest moods, and says so.

**How the catalogue grows (curator in the loop):**
1. In a chat, or in the weekly background run that targets the biggest gaps, the agent finds a song on a trusted site, completes its details and suggests a mood with its basis.
2. You confirm, and it goes to a review queue. Updates to a waiting suggestion change it rather than duplicate it.
3. The owner accepts, edits or rejects it, in the page's Review panel or the terminal. Accepted songs can go live in the page at once.
4. Importing to the repo writes the CSVs, checks the whole catalogue and rolls back on any error.
5. The page is rebuilt from the repo. The agent can never approve its own suggestions.

**How it stays correct:**
- **86 offline tests.** They include 231 identical calls run through both the Python agent and the chat page, which must give identical answers.
- **42 live evals** of real conversations covering facts, grounding, moods, taste, scope and safety.
- **The rules,** written in [agent-behaviour-rules.md](agent-behaviour-rules.md).

**Repo map:**

| Path | Role |
|---|---|
| `data/` | The catalogue: raagas, krithis, moods (source of truth) |
| `carnatic/` | Python agent, tools, taste profile, proposals and review |
| `web/` | The chat page (`template.html` → built `index.html`) |
| `tests/`, `evals/` | Offline tests and live evals |
| `docs/` | This overview and the behaviour rules |
