# Use ManoRaga with your own Claude subscription

This puts the ManoRaga chat page into **your own** Claude account: the same page, the same chat, cards and taste
panel the maintainer uses. Chats count toward your own Claude plan's usage. No API key, no extra cost, nothing
hosted anywhere else.

## What you need
- A Claude account (claude.ai) with **Settings → Capabilities → Code execution and file creation** turned on
  (artifacts need it).
- For web search on the trusted sources: the free **Parallel Search** connector. Add it in **Settings → Connectors**
  (search the directory for "Parallel Search"). Without it ManoRaga still works from its catalogue and gives you
  search links instead.

## Set it up (about 2 minutes)
1. Download `web/index.html` from this repo (or `git clone` the repo).
2. Start a new chat on claude.ai, attach `index.html`, and send this message:

   > Publish the attached index.html as a new artifact for me, exactly as it is (don't edit it). Title: "ManoRaga",
   > icon: "music". Then declare these capabilities on it, exactly:
   > `{"sample": {}, "user": {}, "downloads": true, "db": {"rules": [{"path": "suggestions", "read": "admin", "write": "self"}, {"path": "suggestions/{self}", "read": "view", "write": "interact"}, {"path": "curation", "read": "admin", "write": "admin"}, {"path": "catalog", "read": "view", "write": "admin"}]}, "mcp": {"servers": [{"server": "Parallel Search", "tools": ["web_search", "web_fetch"]}]}}`
   > Then give me the link.

3. Open the link. The first time you chat, Claude asks you to allow ManoRaga to use Claude, and the first web search
   asks you to allow Parallel Search. Say yes to both.

Using Claude Code instead? Open the cloned repo and say "set up ManoRaga in my Claude account". The skill in
`.claude/skills/install-manoraga/` does the same steps.

## What's yours
- Your taste profile (likes, notes on songs, level, languages) is saved privately in your copy.
- Corrections and songs you ask to add go to **your** copy's suggestion box. As the owner of your copy you get a
  **Review** button in the header: accept, fix or reject each suggestion, then **Export for the repo**. To get them
  into the shared catalogue, open an issue on this GitHub repo and attach the exported `manoraga-suggestions.json`.

## Updating
When the repo changes (new songs, fixes): `git pull` (or download `web/index.html` again), then in a Claude chat
attach the new file and say: "Republish my ManoRaga artifact with the attached index.html, unchanged, and make sure
its capabilities match SETUP_IN_CLAUDE.md." Your saved taste and review decisions stay.
