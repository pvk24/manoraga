// Replays suggestion-box sends through the page's mergeIntoBox (catalogue core) for tests/test_review_export.py.
// stdin: {"html": "...", "sends": [entry, ...]}  stdout: the resulting box items
const vm = require("vm");
let input = "";
process.stdin.on("data", (d) => (input += d));
process.stdin.on("end", () => {
  const { html, sends } = JSON.parse(input);
  const catLine = html.match(/^const CAT = .*;$/m)[0];
  const core = html.slice(html.indexOf("/*@core-begin"), html.indexOf("/*@core-end*/"));
  const stubs = "const $ = () => null; function renderTaste() {} function refreshCards() {} const use = () => Promise.resolve(null);";
  const code = stubs + "\n" + catLine + "\n" + core + `
    const items = []; let n = 0;
    for (const e of SENDS) { const ts = '2026-11-21T12:0' + (n++) + ':00Z'; if (!mergeIntoBox(items, e, ts)) items.push({...e, id: 'id' + n, ts, status: 'pending'}); }
    RESULT = JSON.stringify(items);`;
  const sb = { SENDS: sends, RESULT: null, Blob, URL, console };
  vm.runInNewContext(code, sb);
  process.stdout.write(sb.RESULT);
});
