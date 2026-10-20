import { test } from "node:test";
import assert from "node:assert/strict";
import {
  LIGHT_MODEL, LIMITS, PRIMARY_MODEL, callCost, globalReserve, globalSettle, registerAllowed, reserve,
  sanitizeRequest, settle, signToken, verifyToken, newInstallId,
} from "../src/logic.js";

const LIM = { monthlyUsd: 2.5, dailyFullGames: 40, dailyMaxGames: 150, perMinute: 6 };
const req = (over = {}) => ({
  model: PRIMARY_MODEL,
  messages: [{ role: "system", content: "You parse logs." }, { role: "user", content: "log" }],
  response_format: { type: "json_object" },
  ...over,
});

test("token round-trips and rejects tampering", async () => {
  const id = newInstallId();
  const token = await signToken("secret-1", id);
  assert.equal(await verifyToken("secret-1", token), id);
  assert.equal(await verifyToken("secret-2", token), null);
  const other = await signToken("secret-1", newInstallId());
  assert.equal(await verifyToken("secret-1", `v1.${id}.${other.split(".")[2]}`), null);
  assert.equal(await verifyToken("secret-1", "sk-proj-abc"), null);
  assert.equal(await verifyToken("secret-1", ""), null);
});

test("sanitize keeps only the app's prompt", () => {
  const { body } = sanitizeRequest(req({ tools: [{}], temperature: 2, n: 5, logit_bias: {} }));
  assert.deepEqual(Object.keys(body).sort(),
    ["max_completion_tokens", "messages", "model", "response_format", "store"]);
  assert.equal(body.store, false);
  assert.equal(body.max_completion_tokens, LIMITS.maxCompletionTokens);
  assert.ok(sanitizeRequest(req({ model: "gpt-5" })).error);
  assert.ok(sanitizeRequest(req({ stream: true })).error);
  assert.ok(sanitizeRequest(req({ messages: [{ role: "user", content: "x" }] })).error);
  assert.ok(sanitizeRequest(req({ messages: [{ role: "system", content: "s" },
    { role: "user", content: [{ type: "image_url" }] }] })).error);
  assert.ok(sanitizeRequest(req({ messages: [{ role: "system", content: "s" },
    { role: "user", content: "x".repeat(LIMITS.maxUserChars + 1) }] })).error);
  assert.ok(sanitizeRequest(null).error);
  assert.ok(sanitizeRequest([]).error);
});

test("light model after the daily allowance", () => {
  assert.equal(sanitizeRequest(req(), { light: true }).body.model, LIGHT_MODEL);
  assert.equal(sanitizeRequest(req({ model: "gpt-4.1-mini" }), { light: true }).body.model, "gpt-4.1-mini");
});

test("reserve: daily switch, hard cap, burst, budget, month reset", () => {
  let s = {};
  const t0 = new Date("2026-10-20T10:00:00Z");
  for (let i = 0; i < 40; i++) {
    const r = reserve(s, LIM, new Date(t0.getTime() + i * 61_000));
    assert.ok(r.ok); assert.equal(r.light, false); s = r.state;
  }
  let r = reserve(s, LIM, new Date(t0.getTime() + 41 * 61_000));
  assert.ok(r.ok && r.light);
  // Burst: 6 per minute.
  s = {};
  for (let i = 0; i < 6; i++) { r = reserve(s, LIM, t0); assert.ok(r.ok); s = r.state; }
  assert.equal(reserve(s, LIM, t0).code, "rate_limited");
  assert.ok(reserve(s, LIM, new Date(t0.getTime() + 60_001)).ok);
  // Daily hard cap.
  assert.equal(reserve({ day: "2026-10-20", games: 150 }, LIM, t0).code, "daily_limit");
  assert.ok(reserve({ day: "2026-10-19", games: 150 }, LIM, t0).ok);
  // Budget, then a new month.
  s = settle({}, 2.5, t0);
  r = reserve(s, LIM, t0);
  assert.equal(r.code, "ai_budget");
  assert.equal(r.reset, "2026-11-01T00:00:00.000Z");
  assert.ok(reserve(s, LIM, new Date("2026-11-01T00:00:01Z")).ok);
});

test("cost matches ai_usage.py", () => {
  const usage = { prompt_tokens: 4000, completion_tokens: 300, prompt_tokens_details: { cached_tokens: 1000 } };
  const c = callCost(PRIMARY_MODEL, usage);
  assert.ok(Math.abs(c - (3000 * 0.20 + 1000 * 0.02 + 300 * 1.25) / 1e6) < 1e-12);
  assert.ok(Math.abs(callCost("unknown", { prompt_tokens: 1e6 }) - 0.40) < 1e-12);
  assert.equal(callCost(PRIMARY_MODEL, undefined), 0);
});

test("global ceiling and registration limit", () => {
  const now = new Date("2026-10-20T10:00:00Z");
  const g = { globalDailyUsd: 10, globalMonthlyUsd: 150 };
  let s = globalSettle({}, 9.99, now);
  assert.ok(globalReserve(s, g, now).ok);
  s = globalSettle(s, 0.02, now);
  assert.equal(globalReserve(s, g, now).code, "service_busy");
  assert.ok(globalReserve(s, g, new Date("2026-10-21T00:00:00Z")).ok);
  let r = { state: {} };
  for (let i = 0; i < 5; i++) { r = registerAllowed(r.state, 5, now); assert.ok(r.ok); }
  assert.equal(registerAllowed(r.state, 5, now).ok, false);
});
