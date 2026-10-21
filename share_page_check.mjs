// Runs the share page's decoder (docs/d/index.html) on cases from test_deck_share.py; must match deck_share.py.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
const root = fileURLToPath(new URL("./", import.meta.url));
const html = readFileSync(root + "docs/d/index.html", "utf8");
const script = html.split("<script>")[1].split("</script>")[0].split("(async () => {")[0];
const mod = new Function("atob", "TextDecoder", "DecompressionStream", "Blob", "Response",
  script + "; return { decode, exportText };")(atob, TextDecoder, DecompressionStream, Blob, Response);
const table = readFileSync(root + "docs/d/cards_v1.txt", "utf8").split("\n").filter(l => l.trim() && !l.startsWith("#"));
const cases = JSON.parse(readFileSync(process.argv[2], "utf8"));
let bad = 0;
for (const c of cases) {
  const text = mod.exportText(await mod.decode(c.token, table));
  if (text !== c.text) { bad++; console.log("MISMATCH", c.token.slice(0, 20)); console.log(text); console.log(c.text); }
}
for (const junk of ["zzz", "a!!!!", "aAAAA", "b" + "A".repeat(40)]) {
  try { await mod.decode(junk, table); console.log("ACCEPTED", junk); bad++; } catch { /* expected */ }
}
console.log(bad ? `${bad} failures` : `all ${cases.length} cases match`);
process.exit(bad ? 1 : 0);
