---
name: import-manoraga
description: Import the ManoRaga suggestion box into the repo's catalogue. Use when the user says "import the ManoRaga suggestion box", "import my ManoRaga suggestions", or clicks this skill.
---

# Import the ManoRaga suggestion box

Brings what the owner accepted or added in the chat page's Review panel into `data/*.csv` in github.com/pvk24/manoraga, then ships it. Undecided suggestions are queued in `proposals.db`; rejected ones are skipped. Re-running is safe.

## Steps
1. **Get the repo.** If `/home/claude/manoraga` (or another clone of pvk24/manoraga) isn't here, attach the repo with add_repo (owner `pvk24`, repo `manoraga`, access `push`), clone it and `cd` into it. Otherwise `git pull`. Run `python -m pytest -q` to confirm a clean start.
2. **Read the page's storage** with the claude-artifacts db tools. The page is the artifact with slug `a4c59f81-baeb-4db9-8b06-96077bf70da9` (the user's own ManoRaga page; if they have another, use `list_artifacts` with query "ManoRaga").
   - `db_whoami` gives the owner id.
   - Save `suggestions/<owner id>` to `/tmp/imp/box.json` and `curation/decisions` to `/tmp/imp/decisions.json`, exactly as stored. Note the decisions version.
3. **Import:** `python scripts/import_box.py /tmp/imp/box.json /tmp/imp/decisions.json`. It runs the page's own export code and imports the result. Read every result line; an error means the entry didn't apply (report it, don't force it).
4. **Mark them exported:** for every id in `exported_ids`, set `"exported": true` in `curation/decisions` with db_write (`set` the whole document, `ifVersion` from step 2; re-read and retry if the version changed). Then the Review panel stops offering them for export.
5. **Ship it** (skip if nothing changed in `data/`):
   - `python scripts/build_web.py`, then `python -m pytest -q`. It must pass before you commit: check its exit code (don't pipe it into `tail` without `set -o pipefail`). If `test_eval_cases` fails, an imported song was an eval's example of a missing song: swap that eval to another song that's genuinely missing (verified on a trusted site) and update `absent_from_catalogue`.
   - Commit with message "Import suggestion box: <names>" and push to main.
   - Republish the page: `get_artifact` for its version, then `publish_files` with `index.html` = `web/index.html` and that `base_version`.
6. **Report** in a few lines: what joined the catalogue (title, raaga, moods), what is queued, anything that failed and why.

Never approve a suggestion the owner didn't accept or add in the page, and never edit `data/` by hand.
