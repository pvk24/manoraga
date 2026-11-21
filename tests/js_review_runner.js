// Runs the page's review/export code (normEntry + merged) in Node for tests/test_review_export.py.
// stdin: {"html": "...", "items": [...suggestion-box entries...], "decisions": {...}}  stdout: export JSON
const vm = require("vm");
let input = "";
process.stdin.on("data", (d) => (input += d));
process.stdin.on("end", () => {
  const { html, items, decisions } = JSON.parse(input);
  const catLine = html.match(/^const CAT = .*;$/m)[0];
  const a = html.indexOf("/* ---------- curator review"), b = html.indexOf("$('#review').addEventListener('click'");
  const code = catLine + "\nconst esc = s => String(s); const MOODS = CAT.moods;\n" + html.slice(a, b) + `
    REV.items = ITEMS.map(it => normEntry(it, it.user || 'u'));
    REV.dec = DECISIONS;
    RESULT = JSON.stringify({format: 'manoraga-suggestions/1', exported_at: 'x', items: REV.items.filter(open_).map(merged)});`;
  const sb = { ITEMS: items, DECISIONS: decisions, RESULT: null, $: () => null, DB: null };
  vm.runInNewContext(code, sb);
  process.stdout.write(sb.RESULT);
});
