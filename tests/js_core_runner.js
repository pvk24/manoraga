// Runs the web page's agent core (catalogue, profile, tools) in Node for tests/test_parity.py.
// stdin: {"html": "<built index.html>", "cases": [{setup: [[tool, args], ...], tool, args}, ...]}
// stdout: JSON array with each tool's raw result.
const vm = require("vm");

let input = "";
process.stdin.on("data", (d) => (input += d));
process.stdin.on("end", () => {
  const { html, cases } = JSON.parse(input);
  const catLine = html.match(/^const CAT = .*;$/m);
  const begin = html.indexOf("/*@core-begin");
  const end = html.indexOf("/*@core-end*/");
  if (!catLine || begin < 0 || end < 0) throw new Error("core markers or catalogue line not found in page");

  const harness = `
    const out = [];
    const tool = (n) => { const t = TOOLS.find((x) => x.name === n); if (!t) throw new Error("no tool " + n); return t; };
    for (const c of CASES) {
      profile = { preferences: {}, feedback: [] }; trace = []; picks = null;   // fresh user per case
      for (const [name, args] of c.setup || []) tool(name).execute(args);
      out.push(tool(c.tool).execute(c.args));
    }
    RESULT = JSON.stringify(out);`;
  // Stubs for the page-only functions the core calls.
  const stubs = "const $ = () => null; function renderTaste() {} function refreshCards() {} const use = () => Promise.resolve(null);";
  const code = stubs + "\n" + catLine[0] + "\n" + html.slice(begin, end) + "\n" + harness;
  const sandbox = { CASES: cases, RESULT: null, Blob, URL, console };
  vm.runInNewContext(code, sandbox, { timeout: 20000 });
  process.stdout.write(sandbox.RESULT);
});
