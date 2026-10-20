// The worker end to end with a fake OpenAI and in-memory Durable Objects
// (each serializes its calls, as Cloudflare does). Replays the pen-test's
// attacks on the limits: parallel overshoot, one network draining the
// global cap, hang-ups, oversized bodies, missing client address.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, writeFileSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

// Load worker.js with the "cloudflare:workers" import replaced by a stub.
const dir = mkdtempSync(join(tmpdir(), "ptcgl-proxy-"));
const src = new URL("../src/", import.meta.url);
for (const f of ["logic.js", "prompt.js"]) writeFileSync(join(dir, f), readFileSync(new URL(f, src)));
writeFileSync(join(dir, "worker.js"), readFileSync(new URL("worker.js", src), "utf8").replace(
  'import { DurableObject } from "cloudflare:workers";',
  "class DurableObject { constructor(ctx, env) { this.ctx = ctx; this.env = env; } }"));
const { default: worker, Quota } = await import(pathToFileURL(join(dir, "worker.js")));
const { signToken, newInstallId, PRIMARY_MODEL } = await import(pathToFileURL(join(dir, "logic.js")));

function makeEnv(vars = {}) {
  const objects = new Map();
  const QUOTA = {
    idFromName: (name) => name,
    get(name) {
      if (!objects.has(name)) {
        const store = new Map();
        const obj = new Quota({ storage: { get: async (k) => store.get(k), put: async (k, v) => { store.set(k, structuredClone(v)); } } }, {});
        let chain = Promise.resolve();
        objects.set(name, new Proxy(obj, { get: (o, m) => (...args) => (chain = chain.then(() => o[m](...args))) }));
      }
      return objects.get(name);
    },
  };
  return { QUOTA, OPENAI_API_KEY: "sk-test-key", TOKEN_SECRET: "secret", AI_ENABLED: "true", ...vars, objects };
}

// Fake OpenAI: a fixed-cost answer after a short delay.
let openaiCalls = 0;
const USAGE = { prompt_tokens: 3000, completion_tokens: 300 };
globalThis.fetch = async (url, init) => {
  openaiCalls += 1;
  assert.equal(url, "https://api.openai.com/v1/chat/completions");
  assert.equal(init.headers.authorization, "Bearer sk-test-key");
  await new Promise((r) => setTimeout(r, 5));
  const content = JSON.stringify({ My_deck: "Gengar ex", OpponentsDeck: "Dragapult ex", Win_or_Loss: "Win",
    Confidence: 70, Candidates: [{ deck: "Dragapult ex", probability: 70 }] });
  return new Response(JSON.stringify({ model: JSON.parse(init.body).model, usage: USAGE,
    choices: [{ message: { content } }] }), { status: 200 });
};

const LOG = ["Setup", "Player drew 7 cards for the opening hand.", "Opponent drew 7 cards for the opening hand.",
  "Turn # 1 - Player's Turn", "Player drew a card.", "Player played Dreepy to the Bench.", "Player ended their turn."].join("\n");
const BODY = { model: PRIMARY_MODEL, battlelog: LOG, decks: ["Dragapult ex"], evidence: null, anonymized: true };

function call(env, path, { token, ip = "203.0.113.9", body = BODY, method = "POST", raw } = {}) {
  const headers = { "content-type": "application/json" };
  if (ip) headers["cf-connecting-ip"] = ip;
  if (token) headers.authorization = `Bearer ${token}`;
  const waits = [];
  const req = new Request(`https://proxy.test${path}`, { method, headers,
    body: method === "GET" ? undefined : raw ?? JSON.stringify(body) });
  return worker.fetch(req, env, { waitUntil: (p) => waits.push(p) }).then(async (res) => {
    await Promise.all(waits);
    return { status: res.status, json: await res.json() };
  });
}

const token = () => signToken("secret", newInstallId());
const spent = async (env, name) => (await env.QUOTA.get(name)._get()).spent || 0;

test("a valid log is parsed; only the five fields come back", async () => {
  const env = makeEnv();
  const r = await call(env, "/v1/parse", { token: await token() });
  assert.equal(r.status, 200);
  assert.deepEqual(Object.keys(r.json.result).sort(), ["Candidates", "Confidence", "My_deck", "OpponentsDeck", "Win_or_Loss"]);
  assert.equal(r.json.result.OpponentsDeck, "Dragapult ex");
  assert.ok(!JSON.stringify(r.json).includes("sk-test-key"));
});

test("parallel calls never push an install past its budget", async () => {
  const env = makeEnv({ MONTHLY_BUDGET_USD: "0.02", DAILY_BUDGET_USD: "1", PER_MINUTE: "50", REQUESTS_PER_MINUTE: "100" });
  const t = await token();
  openaiCalls = 0;
  const results = await Promise.all(Array.from({ length: 30 }, () => call(env, "/v1/parse", { token: t })));
  const ok = results.filter((r) => r.status === 200).length;
  assert.ok(ok > 0 && ok < 30, `${ok} succeeded`);
  assert.equal(openaiCalls, ok);
  // Real cost is recorded; it can't exceed the budget because each call was pre-charged at its worst case.
  const installs = [...env.objects.keys()].filter((k) => k.startsWith("install:"));
  assert.ok((await spent(env, installs[0])) <= 0.02 + 1e-12);
});

test("one network can't drain the global cap", async () => {
  const env = makeEnv({ NETWORK_DAILY_USD: "0.01", PER_MINUTE: "1000", REQUESTS_PER_MINUTE: "1000",
    DAILY_BUDGET_USD: "1", REGISTER_PER_IP_PER_DAY: "1000" });
  const tokens = await Promise.all(Array.from({ length: 5 }, token));
  let ok = 0;
  for (let i = 0; i < 60; i++) if ((await call(env, "/v1/parse", { token: tokens[i % 5] })).status === 200) ok += 1;
  assert.ok((await spent(env, "global")) <= 0.01 + 1e-12);
  // Another network still gets through.
  assert.equal((await call(env, "/v1/parse", { token: await token(), ip: "198.51.100.7" })).status, 200);
  assert.ok(ok < 60);
});

test("an IPv6 /64 is one network for registrations", async () => {
  const env = makeEnv();
  let ok = 0;
  for (let i = 0; i < 20; i++) {
    const r = await call(env, "/v1/register", { ip: `2001:db8:1:2::${(i + 1).toString(16)}`, body: {} });
    if (r.status === 200) ok += 1;
  }
  assert.equal(ok, 5);
  assert.equal((await call(env, "/v1/register", { ip: "2001:db8:1:3::1", body: {} })).status, 200);
});

test("no client address, bad tokens, oversized and malformed bodies are refused", async () => {
  const env = makeEnv();
  const t = await token();
  assert.equal((await call(env, "/v1/parse", { token: t, ip: null })).status, 400);
  assert.equal((await call(env, "/v1/register", { ip: null, body: {} })).status, 400);
  assert.equal((await call(env, "/v1/parse", { token: "v1.forged.token" })).status, 401);
  assert.equal((await call(env, "/v1/parse", { token: t, raw: "x".repeat(300_000) })).status, 413);
  assert.equal((await call(env, "/v1/parse", { token: t, raw: "{not json" })).status, 400);
  assert.equal((await call(env, "/v1/parse", { token: t, body: { ...BODY, anonymized: false } })).status, 400);
  assert.equal((await call(env, "/v1/chat/completions", { token: t })).status, 404);
});

test("invalid requests are rate-limited before validation", async () => {
  const env = makeEnv();
  const t = await token();
  const statuses = [];
  for (let i = 0; i < 15; i++) statuses.push((await call(env, "/v1/parse", { token: t, body: { junk: true } })).status);
  assert.deepEqual(statuses.slice(0, 12), Array(12).fill(400));
  assert.ok(statuses.slice(12).every((s) => s === 429));
});

test("a failed upstream call is released in full", async () => {
  const env = makeEnv();
  const t = await token();
  const saved = globalThis.fetch;
  globalThis.fetch = async () => new Response("boom", { status: 500 });
  try {
    assert.equal((await call(env, "/v1/parse", { token: t })).status, 502);
  } finally {
    globalThis.fetch = saved;
  }
  assert.equal(await spent(env, "global"), 0);
  const install = [...env.objects.keys()].find((k) => k.startsWith("install:"));
  const s = await env.QUOTA.get(install)._get();
  assert.equal(s.spent, 0); assert.equal(s.games, 0);
});

test("kill switch", async () => {
  const env = makeEnv({ AI_ENABLED: "false" });
  assert.equal((await call(env, "/v1/parse", { token: await token() })).status, 503);
});
