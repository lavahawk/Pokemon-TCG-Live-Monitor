// PTCGL Monitor AI proxy (Cloudflare Worker).
//
// The OpenAI key lives only here, as an encrypted Worker secret. The app
// talks to this worker over HTTPS with a per-install token; the worker checks
// the token, accepts nothing but an anonymized Pokémon TCG Live battle log
// (prompt.js checks it line by line, builds the prompt itself and returns
// only the deck fields), enforces the limits, and calls OpenAI.
//
// Routes:
//   POST /v1/register  -> {token}                                  (per network per day)
//   POST /v1/parse     Authorization: Bearer <token>
//                      {model, battlelog, decks, evidence, anonymized: true}
//                      -> {result: {My_deck, OpponentsDeck, Win_or_Loss, Confidence, Candidates}, model, usage}
//   GET  /v1/status    Authorization: Bearer <token> -> {budget_left, reset}
//
// Limits (each call pre-charged with its worst-case cost, settled after):
//   per install: monthly + daily USD, games per day, calls per minute, requests per minute
//   per network (IPv4 address / IPv6 /64): daily USD, new installs per day
//   all installs: daily + monthly USD
//
// Secrets: OPENAI_API_KEY, TOKEN_SECRET (wrangler secret put ...).
// Vars (wrangler.toml): limits and the AI_ENABLED kill switch.

import { DurableObject } from "cloudflare:workers";
import {
  LIGHT_MODEL, LIMITS, MODEL_ORDER, PRIMARY_MODEL, callCost, estimateCost, networkKey, newInstallId,
  nextMonthStart, registerAllowed, reserve, settle, sha256Hex, signToken, touch, verifyToken,
} from "./logic.js";
import { SYSTEM_PROMPT, checkParseRequest, renderPrompt, sanitizeResult } from "./prompt.js";

const OPENAI_URL = "https://api.openai.com/v1/chat/completions";

function json(status, payload, extra = {}) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "content-type": "application/json", "cache-control": "no-store", ...extra },
  });
}

function fail(status, code, message, extra) {
  return json(status, { error: { code, message, type: "proxy_error" } }, extra);
}

function limits(env) {
  const num = (v, d) => (Number.isFinite(Number(v)) && v !== "" && v != null ? Number(v) : d);
  return {
    install: {
      monthlyUsd: num(env.MONTHLY_BUDGET_USD, 2.5),
      dailyUsd: num(env.DAILY_BUDGET_USD, 0.25),
      dailyFullGames: num(env.DAILY_FULL_GAMES, 40),
      dailyMaxGames: num(env.DAILY_MAX_GAMES, 150),
      perMinute: num(env.PER_MINUTE, 6),
    },
    requestsPerMinute: num(env.REQUESTS_PER_MINUTE, 12),
    network: { monthlyUsd: Infinity, dailyUsd: num(env.NETWORK_DAILY_USD, 1), dayCode: "daily_limit" },
    global: {
      monthlyUsd: num(env.GLOBAL_MONTHLY_USD, 150), dailyUsd: num(env.GLOBAL_DAILY_USD, 10),
      overCode: "service_busy", dayCode: "service_busy",
    },
    registerPerNetworkDay: num(env.REGISTER_PER_IP_PER_DAY, 5),
  };
}

function counter(env, name) {
  return env.QUOTA.get(env.QUOTA.idFromName(name));
}

// kind: "net" (spend) or "reg" (new installs): separate counters.
async function networkCounterName(request, kind) {
  const key = networkKey(request.headers.get("cf-connecting-ip"));
  // Hashed: no address is stored.
  return key ? `${kind}:${await sha256Hex(key)}` : null;
}

// The body, read with a byte cap (a missing or lying Content-Length can't
// make the worker buffer more than maxBodyBytes).
async function readJson(request) {
  const declared = Number(request.headers.get("content-length") || 0);
  if (declared > LIMITS.maxBodyBytes) return { tooBig: true };
  if (!request.body) return { body: null };
  const reader = request.body.getReader();
  const chunks = [];
  let size = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    size += value.byteLength;
    if (size > LIMITS.maxBodyBytes) {
      await reader.cancel();
      return { tooBig: true };
    }
    chunks.push(value);
  }
  const bytes = new Uint8Array(size);
  let at = 0;
  for (const c of chunks) { bytes.set(c, at); at += c.byteLength; }
  try { return { body: JSON.parse(new TextDecoder().decode(bytes)) }; } catch { return { body: null }; }
}

async function authed(request, env) {
  const auth = request.headers.get("authorization") || "";
  const token = auth.startsWith("Bearer ") ? auth.slice(7).trim() : "";
  return verifyToken(env.TOKEN_SECRET, token);
}

async function register(request, env) {
  const net = await networkCounterName(request, "reg");
  if (!net) return fail(400, "bad_request", "No client address.");
  const gate = await counter(env, net).registerNet(limits(env).registerPerNetworkDay);
  if (!gate.ok) return fail(429, "register_limit", "Too many new installs from this network today.");
  return json(200, { token: await signToken(env.TOKEN_SECRET, newInstallId()) });
}

async function status(installId, env) {
  return json(200, await counter(env, `install:${installId}`).info(limits(env).install.monthlyUsd));
}

async function parse(request, env, ctx, installId) {
  const lim = limits(env);
  const quota = counter(env, `install:${installId}`);
  // Cheap gate before reading or validating anything.
  if (!(await quota.touch(lim.requestsPerMinute)).ok)
    return fail(429, "rate_limited", "Too many AI requests; try later.");
  const net = await networkCounterName(request, "net");
  if (!net) return fail(400, "bad_request", "No client address.");
  const { body, tooBig } = await readJson(request);
  if (tooBig) return fail(413, "too_large", "Request too large.");
  const checked = checkParseRequest(body, MODEL_ORDER);
  if (checked.error) return fail(400, "bad_request", checked.error);
  const fields = checked.fields;
  const prompt = renderPrompt(fields);
  // Pre-charge the worst case for the requested model (the light model the
  // install may be switched to is never dearer).
  const estimate = estimateCost(fields.model, SYSTEM_PROMPT + prompt);

  // Pre-charge network, then everyone, then the install; undo on refusal.
  const network = counter(env, net), world = counter(env, "global");
  const n = await network.reserve(lim.network, estimate);
  if (!n.ok) return fail(429, "daily_limit", "Too many AI requests from this network today.");
  const g = await world.reserve(lim.global, estimate);
  if (!g.ok) {
    await network.settle(-estimate);
    return fail(503, "service_busy", "AI detection is busy right now; manual mode for this game.");
  }
  const r = await quota.reserve(lim.install, estimate, true);
  if (!r.ok) {
    await Promise.all([network.settle(-estimate), world.settle(-estimate)]);
    const msg = r.code === "ai_budget" ? "Monthly AI allowance used." : "Too many AI requests; try later.";
    return fail(429, r.code, msg, r.reset ? { "x-ai-reset": r.reset } : {});
  }

  const upstream = {
    // After the daily allowance the light model leads (as in ai_usage.py).
    model: r.light && fields.model === PRIMARY_MODEL ? LIGHT_MODEL : fields.model,
    messages: [{ role: "system", content: SYSTEM_PROMPT }, { role: "user", content: prompt }],
    response_format: { type: "json_object" },
    max_completion_tokens: LIMITS.maxCompletionTokens,
    store: false,
    safety_identifier: (await sha256Hex(`sid:${installId}`)).slice(0, 32),
  };

  // The call and its settlement run to the end even if the app hangs up.
  const work = (async () => {
    let res, text = "";
    try {
      res = await fetch(OPENAI_URL, {
        method: "POST",
        headers: { authorization: `Bearer ${env.OPENAI_API_KEY}`, "content-type": "application/json" },
        body: JSON.stringify(upstream),
      });
      text = await res.text();
    } catch {
      res = null;
    }
    let data = null;
    if (res && res.ok) { try { data = JSON.parse(text); } catch { data = null; } }
    // A failed call is released; a completed one is settled at its real
    // cost (normally below the pre-charge; recorded in full if not).
    const cost = data ? callCost(data.model || upstream.model, data.usage) : 0;
    const delta = cost - estimate;
    await Promise.all([quota.settle(delta, !data), network.settle(delta), world.settle(delta)]);
    if (!res) return fail(502, "upstream_unreachable", "AI service unreachable.");
    if (!res.ok) {
      // Never echo OpenAI's error body: it can name the account or the key.
      console.log(`upstream ${res.status} for ${upstream.model}: ${text.slice(0, 300)}`);
      return fail(res.status === 429 ? 503 : 502, "upstream_error", `AI model ${upstream.model} failed (${res.status}).`);
    }
    const result = sanitizeResult(data?.choices?.[0]?.message?.content);
    if (!result) return fail(502, "upstream_error", `AI model ${upstream.model} gave no usable answer.`);
    const u = data.usage || {};
    return json(200, {
      result,
      model: String(data.model || upstream.model),
      usage: {
        prompt_tokens: Number(u.prompt_tokens) || 0,
        completion_tokens: Number(u.completion_tokens) || 0,
        prompt_tokens_details: { cached_tokens: Number(u.prompt_tokens_details?.cached_tokens) || 0 },
      },
    });
  })();
  ctx.waitUntil(work);
  return work;
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const path = url.pathname.replace(/\/+$/, "");
    if (String(env.AI_ENABLED).toLowerCase() === "false")
      return fail(503, "service_busy", "AI detection is paused.");
    if (!env.OPENAI_API_KEY || !env.TOKEN_SECRET) return fail(503, "not_configured", "Proxy not configured.");
    try {
      if (path === "/v1/register" && request.method === "POST") return await register(request, env);
      if (path === "/v1/parse" || path === "/v1/status") {
        const installId = await authed(request, env);
        if (!installId) return fail(401, "invalid_token", "Unknown install.");
        if (path === "/v1/status" && request.method === "GET") return await status(installId, env);
        if (path === "/v1/parse" && request.method === "POST") return await parse(request, env, ctx, installId);
      }
      return fail(404, "not_found", "Not found.");
    } catch (err) {
      console.log(`proxy error: ${err && err.stack}`);
      return fail(500, "proxy_error", "Proxy error.");
    }
  },
};

// One instance per counter name ("install:<id>", "net:<hash>", "reg:<hash>", "global"); a
// Durable Object handles its calls one at a time, so the counters are exact.
export class Quota extends DurableObject {
  async _get() { return (await this.ctx.storage.get("s")) || {}; }
  async _put(s) { await this.ctx.storage.put("s", s); }

  async touch(perMinute) {
    const r = touch(await this._get(), perMinute, new Date());
    await this._put(r.state);
    return { ok: r.ok };
  }

  async reserve(lim, estimate, isGame = false) {
    const r = reserve(await this._get(), lim, new Date(), estimate, isGame);
    if (r.ok) await this._put(r.state);
    return { ok: r.ok, code: r.code, reset: r.reset, light: r.light };
  }

  async settle(delta, ungame = false) {
    await this._put(settle(await this._get(), delta, new Date(), ungame));
  }

  async info(monthlyUsd) {
    const now = new Date();
    const s = await this._get();
    const spent = s.month === now.toISOString().slice(0, 7) ? Number(s.spent) || 0 : 0;
    return { budget_left: Math.max(0, monthlyUsd - spent), reset: nextMonthStart(now) };
  }

  async registerNet(limit) {
    const r = registerAllowed(await this._get(), limit, new Date());
    await this._put(r.state);
    return { ok: r.ok };
  }
}
