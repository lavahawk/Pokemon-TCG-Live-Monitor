// PTCGL Monitor AI proxy (Cloudflare Worker).
//
// The OpenAI key lives only here, as an encrypted Worker secret. The app
// talks to this worker over HTTPS with a per-install token; the worker checks
// the token, refuses anything but the app's battle-log prompt, enforces the
// per-install and global limits, and forwards the call to OpenAI.
//
// Routes (OpenAI-compatible where the app's SDK expects it):
//   POST /v1/register          -> {token}            (rate-limited per IP)
//   POST /v1/chat/completions  Authorization: Bearer <token>
//   GET  /v1/status            Authorization: Bearer <token> -> {budget_left, reset}
//
// Secrets: OPENAI_API_KEY, TOKEN_SECRET (wrangler secret put ...).
// Vars (wrangler.toml): limits and the AI_ENABLED kill switch.

import { DurableObject } from "cloudflare:workers";
import {
  LIMITS, callCost, globalReserve, globalSettle, newInstallId, nextMonthStart, registerAllowed,
  reserve, sanitizeRequest, settle, sha256Hex, signToken, verifyToken,
} from "./logic.js";

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
  const num = (v, d) => (Number.isFinite(Number(v)) && v !== "" ? Number(v) : d);
  return {
    monthlyUsd: num(env.MONTHLY_BUDGET_USD, 2.5),
    dailyFullGames: num(env.DAILY_FULL_GAMES, 40),
    dailyMaxGames: num(env.DAILY_MAX_GAMES, 150),
    perMinute: num(env.PER_MINUTE, 6),
    globalDailyUsd: num(env.GLOBAL_DAILY_USD, 10),
    globalMonthlyUsd: num(env.GLOBAL_MONTHLY_USD, 150),
    registerPerIpDay: num(env.REGISTER_PER_IP_PER_DAY, 5),
  };
}

function counter(env, name) {
  return env.QUOTA.get(env.QUOTA.idFromName(name));
}

async function readJson(request) {
  const length = Number(request.headers.get("content-length") || 0);
  if (length > LIMITS.maxBodyBytes) return { tooBig: true };
  const text = await request.text();
  if (text.length > LIMITS.maxBodyBytes) return { tooBig: true };
  try { return { body: JSON.parse(text) }; } catch { return { body: null }; }
}

async function authed(request, env) {
  const auth = request.headers.get("authorization") || "";
  const token = auth.startsWith("Bearer ") ? auth.slice(7).trim() : "";
  return verifyToken(env.TOKEN_SECRET, token);
}

async function register(request, env) {
  const ip = request.headers.get("cf-connecting-ip") || "unknown";
  // The IP is only used hashed, as a counter name.
  const gate = await counter(env, `ip:${await sha256Hex(ip)}`).registerIp(limits(env).registerPerIpDay);
  if (!gate.ok) return fail(429, "register_limit", "Too many new installs from this network today.");
  const installId = newInstallId();
  return json(200, { token: await signToken(env.TOKEN_SECRET, installId) });
}

async function status(installId, env) {
  const info = await counter(env, `install:${installId}`).info(limits(env));
  return json(200, info);
}

async function complete(request, env, installId) {
  const { body, tooBig } = await readJson(request);
  if (tooBig) return fail(413, "too_large", "Request too large.");
  const lim = limits(env);
  // Validate before counting a game against the install.
  const probe = sanitizeRequest(body);
  if (probe.error) return fail(400, "bad_request", probe.error);

  const world = counter(env, "global");
  const g = await world.globalCheck(lim);
  if (!g.ok) return fail(503, "service_busy", "AI detection is busy right now; manual mode for this game.");

  const quota = counter(env, `install:${installId}`);
  const r = await quota.reserve(lim);
  if (!r.ok) {
    const msg = r.code === "ai_budget" ? "Monthly AI allowance used." : "Too many AI requests; try later.";
    return fail(429, r.code, msg, r.reset ? { "x-ai-reset": r.reset } : {});
  }

  const { body: upstream } = sanitizeRequest(body, { light: r.light });
  upstream.safety_identifier = (await sha256Hex(`sid:${installId}`)).slice(0, 32);
  let res;
  try {
    res = await fetch(OPENAI_URL, {
      method: "POST",
      headers: { authorization: `Bearer ${env.OPENAI_API_KEY}`, "content-type": "application/json" },
      body: JSON.stringify(upstream),
    });
  } catch {
    await quota.refund();
    return fail(502, "upstream_unreachable", "AI service unreachable.");
  }
  const text = await res.text();
  if (!res.ok) {
    await quota.refund();
    // Never echo OpenAI's error body: it can name the account or the key.
    console.log(`upstream ${res.status} for ${upstream.model}: ${text.slice(0, 300)}`);
    const status = res.status === 429 ? 503 : 502;
    return fail(status, "upstream_error", `AI model ${upstream.model} failed (${res.status}).`);
  }
  let data;
  try { data = JSON.parse(text); } catch { return fail(502, "upstream_error", "Bad AI response."); }
  const cost = callCost(data.model || upstream.model, data.usage);
  const after = await quota.settle(cost);
  await world.globalAdd(cost);
  return json(200, data, { "x-ai-budget-left": String(Math.max(0, lim.monthlyUsd - after.spent).toFixed(4)) });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname.replace(/\/+$/, "");
    if (String(env.AI_ENABLED).toLowerCase() === "false")
      return fail(503, "service_busy", "AI detection is paused.");
    if (!env.OPENAI_API_KEY || !env.TOKEN_SECRET) return fail(503, "not_configured", "Proxy not configured.");
    try {
      if (path === "/v1/register" && request.method === "POST") return await register(request, env);
      if (path === "/v1/chat/completions" || path === "/v1/status") {
        const installId = await authed(request, env);
        if (!installId) return fail(401, "invalid_token", "Unknown install.");
        if (path === "/v1/status" && request.method === "GET") return await status(installId, env);
        if (path === "/v1/chat/completions" && request.method === "POST")
          return await complete(request, env, installId);
      }
      return fail(404, "not_found", "Not found.");
    } catch (err) {
      console.log(`proxy error: ${err && err.stack}`);
      return fail(500, "proxy_error", "Proxy error.");
    }
  },
};

// One instance per counter name ("install:<id>", "ip:<hash>", "global"); a
// Durable Object handles its calls one at a time, so the counters are exact.
export class Quota extends DurableObject {
  async _get() { return (await this.ctx.storage.get("s")) || {}; }
  async _put(s) { await this.ctx.storage.put("s", s); }

  async reserve(lim) {
    const r = reserve(await this._get(), lim, new Date());
    await this._put(r.state);
    return { ok: r.ok, code: r.code, reset: r.reset, light: r.light };
  }

  async refund() {
    const s = await this._get();
    if (s.games > 0) { s.games -= 1; await this._put(s); }
  }

  async settle(cost) {
    const s = settle(await this._get(), cost, new Date());
    await this._put(s);
    return { spent: s.spent };
  }

  async info(lim) {
    const now = new Date();
    const r = reserve(await this._get(), { ...lim, dailyMaxGames: Infinity, perMinute: Infinity }, now);
    const spent = r.state.month ? r.state.spent : 0;
    return { budget_left: Math.max(0, lim.monthlyUsd - spent), reset: nextMonthStart(now) };
  }

  async globalCheck(lim) {
    const r = globalReserve(await this._get(), lim, new Date());
    await this._put(r.state);
    return { ok: r.ok };
  }

  async globalAdd(cost) { await this._put(globalSettle(await this._get(), cost, new Date())); }

  async registerIp(limit) {
    const r = registerAllowed(await this._get(), limit, new Date());
    await this._put(r.state);
    return { ok: r.ok };
  }
}
