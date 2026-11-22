// Applies export-format entries with the page's checkChange/applyChange (catalogue core) for tests/test_review_export.py.
// stdin: {"html": "...", "items": [...]}  stdout: {"results": [{error|null}], "krithis": [...], "raagas": [...]}
const vm = require("vm");
let input = "";
process.stdin.on("data", (d) => (input += d));
process.stdin.on("end", () => {
  const { html, items } = JSON.parse(input);
  const catLine = html.match(/^const CAT = .*;$/m)[0];
  const core = html.slice(html.indexOf("/*@core-begin"), html.indexOf("/*@core-end*/"));
  const stubs = "const $ = () => null; function renderTaste() {} function refreshCards() {} const use = () => Promise.resolve(null);";
  const code = stubs + "\n" + catLine + "\n" + core + `
    const results = ITEMS.map(it => { const err = checkChange(it); if (!err) applyChange(it, '2026-11-21'); return {error: err}; });
    RESULT = JSON.stringify({results, krithis: CAT.krithis, raagas: CAT.raagas, moods: CAT.moods});`;
  const sb = { ITEMS: items, RESULT: null, Blob, URL, console };
  vm.runInNewContext(code, sb);
  process.stdout.write(sb.RESULT);
});
