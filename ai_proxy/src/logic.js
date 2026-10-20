// Pure helpers for the AI proxy (no Cloudflare APIs), unit-tested in
// test/logic.test.mjs. The worker (worker.js) wires them to requests,
// Durable Objects and OpenAI.

// Same order and prices as the app's ai_usage.py (USD per 1M tokens:
// input, cached input, output).
export const PRIMARY_MODEL = "gpt-5.4-nano-2026-03-17";
export const LIGHT_MODEL = "gpt-4.1-nano";
export const MODEL_ORDER = [PRIMARY_MODEL, LIGHT_MODEL, "gpt-4.1-mini"];
export const PRICES = {
  "gpt-5.4-nano": [0.20, 0.02, 1.25],
  "gpt-4.1-nano": [0.10, 0.025, 0.40],
  "gpt-4.1-mini": [0.40, 0.10, 1.60],
};
const FALLBACK_PRICE = [0.40, 0.10, 1.60];

export const LIMITS = {
  maxBodyBytes: 250_000,
  maxCompletionTokens: 2_000,  // the reply is ~150 tokens; reasoning tokens count here too
};

const enc = new TextEncoder();

export function b64url(bytes) {
  let s = "";
  for (const b of new Uint8Array(bytes)) s += String.fromCharCode(b);
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export function b64urlDecode(text) {
  const s = text.replace(/-/g, "+").replace(/_/g, "/");
  const bin = atob(s + "===".slice((s.length + 3) % 4));
  return Uint8Array.from(bin, (c) => c.charCodeAt(0));
}

async function hmacKey(secret) {
  return crypto.subtle.importKey("raw", enc.encode(secret), { name: "HMAC", hash: "SHA-256" }, false,
    ["sign", "verify"]);
}

export function newInstallId() {
  return b64url(crypto.getRandomValues(new Uint8Array(16)));
}

// Install token = "v1.<installId>.<HMAC-SHA256(secret, 'v1.'+installId)>".
// Stateless: only the server's TOKEN_SECRET can mint one.
export async function signToken(secret, installId) {
  const sig = await crypto.subtle.sign("HMAC", await hmacKey(secret), enc.encode(`v1.${installId}`));
  return `v1.${installId}.${b64url(sig)}`;
}

// The install id when the token is genuine, else null (constant-time check).
export async function verifyToken(secret, token) {
  const m = /^v1\.([A-Za-z0-9_-]{22})\.([A-Za-z0-9_-]{43})$/.exec(String(token || ""));
  if (!m) return null;
  const ok = await crypto.subtle.verify("HMAC", await hmacKey(secret), b64urlDecode(m[2]),
    enc.encode(`v1.${m[1]}`));
  return ok ? m[1] : null;
}

export async function sha256Hex(text) {
  const digest = await crypto.subtle.digest("SHA-256", enc.encode(text));
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

export function price(model) {
  for (const [prefix, p] of Object.entries(PRICES)) if (String(model || "").startsWith(prefix)) return p;
  return FALLBACK_PRICE;
}

// USD for one call from OpenAI's usage block (dearest price if unknown).
export function callCost(model, usage) {
  const [inp, cached, out] = price(model);
  const prompt = Math.max(0, Number(usage?.prompt_tokens) || 0);
  const hit = Math.min(prompt, Math.max(0, Number(usage?.prompt_tokens_details?.cached_tokens) || 0));
  const output = Math.max(0, Number(usage?.completion_tokens) || 0);
  return ((prompt - hit) * inp + hit * cached + output * out) / 1_000_000;
}

export function monthKey(now) { return now.toISOString().slice(0, 7); }
export function dayKey(now) { return now.toISOString().slice(0, 10); }

export function nextMonthStart(now) {
  return new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth() + 1, 1)).toISOString();
}

// Per-install quota state machine (kept in a Durable Object, so updates are
// serialized). state: {month, spent, day, games, recent: [ms]}.
// limits: {monthlyUsd, dailyFullGames, dailyMaxGames, perMinute}.
export function reserve(state, limits, now) {
  const s = { month: "", spent: 0, day: "", games: 0, recent: [], ...state };
  const month = monthKey(now), day = dayKey(now), ms = now.getTime();
  if (s.month !== month) { s.month = month; s.spent = 0; }
  if (s.day !== day) { s.day = day; s.games = 0; }
  s.recent = s.recent.filter((t) => ms - t < 60_000);
  if (s.spent >= limits.monthlyUsd)
    return { state: s, ok: false, code: "ai_budget", reset: nextMonthStart(now) };
  if (s.games >= limits.dailyMaxGames) return { state: s, ok: false, code: "daily_limit" };
  if (s.recent.length >= limits.perMinute) return { state: s, ok: false, code: "rate_limited" };
  s.games += 1;
  s.recent.push(ms);
  return { state: s, ok: true, light: s.games > limits.dailyFullGames, left: limits.monthlyUsd - s.spent };
}

export function settle(state, cost, now) {
  const s = { month: "", spent: 0, ...state };
  if (s.month !== monthKey(now)) { s.month = monthKey(now); s.spent = 0; }
  s.spent += Math.max(0, Number(cost) || 0);
  return s;
}

// Spend ceiling across every install (kill switch against abuse).
export function globalReserve(state, limits, now) {
  const s = { day: "", spent: 0, month: "", monthSpent: 0, ...state };
  if (s.day !== dayKey(now)) { s.day = dayKey(now); s.spent = 0; }
  if (s.month !== monthKey(now)) { s.month = monthKey(now); s.monthSpent = 0; }
  const ok = s.spent < limits.globalDailyUsd && s.monthSpent < limits.globalMonthlyUsd;
  return { state: s, ok, code: ok ? undefined : "service_busy" };
}

export function globalSettle(state, cost, now) {
  const s = globalReserve(state, { globalDailyUsd: Infinity, globalMonthlyUsd: Infinity }, now).state;
  const c = Math.max(0, Number(cost) || 0);
  s.spent += c;
  s.monthSpent += c;
  return s;
}

// New installs per IP per day (anonymous registration is the weak spot:
// each install gets its own monthly allowance).
export function registerAllowed(state, limit, now) {
  const s = { day: "", count: 0, ...state };
  if (s.day !== dayKey(now)) { s.day = dayKey(now); s.count = 0; }
  if (s.count >= limit) return { state: s, ok: false };
  s.count += 1;
  return { state: s, ok: true };
}
