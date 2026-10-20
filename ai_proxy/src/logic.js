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

// Spend counters. Every call is PRE-CHARGED with its worst-case cost
// (estimateCost) before OpenAI is called, so parallel requests or a client
// that hangs up can't push spend past a limit; the difference to the real
// cost is settled afterwards. Each counter lives in its own Durable Object,
// so its updates are serialized.

// Worst case for one call: ASCII at ~3 characters a token (real text is ~4),
// anything else (accents, other scripts) at 1 token a character, plus the
// full completion allowance.
export function estimateCost(model, prompt) {
  const text = String(prompt || "");
  const ascii = text.replace(/[^\x00-\x7f]/g, "").length;
  const tokens = Math.ceil(ascii / 3) + (text.length - ascii);
  return callCost(model, { prompt_tokens: tokens, completion_tokens: LIMITS.maxCompletionTokens });
}

function rolled(state, now) {
  const s = { month: "", spent: 0, day: "", daySpent: 0, games: 0, recent: [], hits: [], ...state };
  if (s.month !== monthKey(now)) { s.month = monthKey(now); s.spent = 0; }
  if (s.day !== dayKey(now)) { s.day = dayKey(now); s.daySpent = 0; s.games = 0; }
  const ms = now.getTime();
  s.recent = s.recent.filter((t) => ms - t < 60_000);
  s.hits = s.hits.filter((t) => ms - t < 60_000);
  return s;
}

// Any request from an install, valid or not, before the body is even read:
// bounds the CPU an install can spend on validation.
export function touch(state, perMinute, now) {
  const s = rolled(state, now);
  if (s.hits.length >= perMinute) return { state: s, ok: false, code: "rate_limited" };
  s.hits.push(now.getTime());
  return { state: s, ok: true };
}

// Pre-charge `estimate` against {dailyUsd, monthlyUsd}; for an install also
// count the game ({dailyMaxGames, perMinute, dailyFullGames}).
export function reserve(state, limits, now, estimate, isGame = false) {
  const s = rolled(state, now);
  const est = Math.max(0, Number(estimate) || 0);
  if (s.spent + est > limits.monthlyUsd)
    return { state: s, ok: false, code: limits.overCode || "ai_budget", reset: nextMonthStart(now) };
  if (s.daySpent + est > limits.dailyUsd) return { state: s, ok: false, code: limits.dayCode || "daily_limit" };
  if (isGame) {
    if (s.games >= limits.dailyMaxGames) return { state: s, ok: false, code: "daily_limit" };
    if (s.recent.length >= limits.perMinute) return { state: s, ok: false, code: "rate_limited" };
    s.games += 1;
    s.recent.push(now.getTime());
  }
  s.spent += est;
  s.daySpent += est;
  return { state: s, ok: true, light: isGame && s.games > limits.dailyFullGames };
}

// Add `delta` (real cost - estimate, or -estimate to release a failed call).
export function settle(state, delta, now, ungame = false) {
  const s = rolled(state, now);
  const d = Number(delta) || 0;
  s.spent = Math.max(0, s.spent + d);
  s.daySpent = Math.max(0, s.daySpent + d);
  if (ungame && s.games > 0) s.games -= 1;
  return s;
}

// New installs per network per day (anonymous registration is the weak
// spot: each install gets its own allowance).
export function registerAllowed(state, limit, now) {
  const s = { day: "", count: 0, ...state };
  if (s.day !== dayKey(now)) { s.day = dayKey(now); s.count = 0; }
  if (s.count >= limit) return { state: s, ok: false };
  s.count += 1;
  return { state: s, ok: true };
}

// The counter name for a client address: IPv6 by its /64 (one household or
// server gets a whole /64), IPv4 as is. null when there is no address.
export function networkKey(ip) {
  let a = String(ip || "").trim().toLowerCase();
  if (!a) return null;
  // IPv4-mapped IPv6 ("::ffff:1.2.3.4") is the IPv4 address.
  const mapped = /^(?:0{0,4}:){0,5}:?ffff:(\d{1,3}(?:\.\d{1,3}){3})$/.exec(a);
  if (mapped) a = mapped[1];
  if (!a.includes(":")) return /^\d{1,3}(\.\d{1,3}){3}$/.test(a) ? a : null;
  const [head, tail] = a.split("::");
  const left = head ? head.split(":") : [];
  const right = tail !== undefined && tail ? tail.split(":") : [];
  const groups = tail !== undefined ? [...left, ...Array(Math.max(0, 8 - left.length - right.length)).fill("0"), ...right] : left;
  if (groups.length < 4 || !groups.slice(0, 4).every((g) => /^[0-9a-f]{1,4}$/.test(g))) return null;
  return groups.slice(0, 4).map((g) => g.replace(/^0+(?=.)/, "")).join(":") + "::/64";
}
