---
name: install-manoraga
description: Publish the ManoRaga chat page (web/index.html) as an artifact in the user's own Claude account, or republish it after an update. Use when the user asks to set up, install, update or republish ManoRaga.
---

# Install ManoRaga in the user's Claude account

The page is already built: `web/index.html` (catalogue embedded). Publish it unchanged; never edit it here.

## New install
1. If the user hasn't pulled recently, suggest `git pull` first so they get the latest catalogue.
2. Read `web/index.html` in full (it is this repo's own page; you must read a file before publishing it).
3. Publish it as a NEW artifact with the artifact tool's publish-files action: file `web/index.html` served as
   `index.html`, title "ManoRaga", icon "music".
4. Then declare capabilities on that artifact, exactly (a new page is published first, then declared):
   ```json
{"sample": {}, "user": {}, "downloads": true, "db": {"rules": [{"path": "suggestions", "read": "admin", "write": "self"}, {"path": "suggestions/{self}", "read": "view", "write": "interact"}, {"path": "curation", "read": "admin", "write": "admin"}, {"path": "catalog", "read": "view", "write": "admin"}]}, "mcp": {"servers": [{"server": "Parallel Search", "tools": ["web_search", "web_fetch"]}]}}
```
5. Give the user the link and tell them:
   - The first chat asks them to allow ManoRaga to use Claude; the first web search asks to allow Parallel Search.
   - Web search needs the free Parallel Search connector (claude.ai Settings → Connectors). Without it the page still
     answers from its catalogue and gives search links.

## Update an existing install
List the user's artifacts, find the one titled "ManoRaga", and republish it with the new `web/index.html`
(base version = its current version). Saved taste and review decisions carry over. Call read_declaration first:
if the capabilities differ from the JSON above, declare the JSON BEFORE republishing (a page gaining a capability
is declared first, then published).

If the artifact tools aren't available in this session, point the user to `SETUP_IN_CLAUDE.md` (the claude.ai
chat route) instead.
