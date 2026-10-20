# AI proxy (built-in AI for the AI edition)

The app never contains the OpenAI key. Any key shipped inside a desktop app can be pulled out of it, whether it is obfuscated, encrypted or compiled, because the app must decrypt it to use it. So the key lives here, in a Cloudflare Worker, stored as an encrypted secret. The app talks to the worker over HTTPS.

```
app ──HTTPS (TLS 1.2+, cert verified)──> Worker ──HTTPS──> OpenAI
     Bearer: per-install token             holds OPENAI_API_KEY (secret)
```

## What protects the key and the bill

- **Key:** the key is only a Worker secret. It is never sent to the app, never logged, and OpenAI error bodies are not passed back.
- **Install token:** on first use the app gets a per-install token, `v1.<id>.<HMAC>`, signed with `TOKEN_SECRET`. The app keeps it DPAPI-encrypted in `.ai_install.dpapi`. Rotating `TOKEN_SECRET` revokes every token, and apps re-register on their own.
- **Battle logs only:** the app never sends a prompt or free text. `POST /v1/parse` takes an anonymized battle log (players are `Player` / `Opponent`), the meta deck names and the card evidence as data (`[deck, %]`, `[card, copies]`), and the model name. The worker:
  - checks the log line by line against the Pokémon TCG Live log grammar (opening hand, turns, plays, card lists, damage breakdowns); at most 3% short unknown lines, 40k characters, 300-character lines, no control characters or `<<`/`>>` markers. Every saved real log passes; prose, indented text and fake card lists do not
  - accepts names (decks, cards) only as 1-6 plain words, so no instructions fit in them
  - builds the prompt itself from a fixed template (`src/prompt.js`, kept identical to the app's by a test), with the log inserted last and marked as data
  - returns only five fields: deck names that must again be 1-6 plain words, the result, a 0-100 confidence and up to 3 candidates. Everything else the model wrote is dropped
  - caps `max_completion_tokens`, forces JSON mode and `store: false`

  A stolen token cannot run other prompts, and anything smuggled into a log gets back at most a few deck-name-shaped words.
- **Limits:** kept in Durable Objects, so the counters are exact. Every call is **pre-charged with its worst-case cost** (the whole prompt plus the full completion allowance) on all three counters before OpenAI is called, then settled at the real cost in `ctx.waitUntil`. Parallel calls or a client that hangs up can't push spend past a limit.

  | Scope | Limit |
  |---|---|
  | Per install | $2.50 a month and $0.25 a day; 40 games a day on the main model, then the light model; 150 games a day; 6 calls and 12 requests a minute (requests are counted before the body is read) |
  | Per network (IPv4 address or IPv6 /64) | $1 a day across its installs; 5 new installs a day |
  | All installs | $10 a day, $150 a month |

- **Kill switch:** set `AI_ENABLED = "false"` and redeploy. Every app falls back to manual mode with no errors.
- **Spend limit at OpenAI:** set a monthly budget on the OpenAI project too, and use a project key limited to the three models.

**Known limit (anonymous installs):** someone with many networks (IPv4 addresses or IPv6 /64s) can still spend up to $1 a day per network until the global $10 a day stops the built-in AI for everyone that day. `/v1/register` is the single place to add a stronger check later (for example Cloudflare Turnstile).

## Deploy (one time, about 10 minutes)

Needs a free Cloudflare account and Node 18+.

```bash
cd ai_proxy
npx wrangler login
npx wrangler secret put OPENAI_API_KEY
npx wrangler secret put TOKEN_SECRET
npx wrangler deploy
```

- `OPENAI_API_KEY`: paste the key; it is never written to disk here.
- `TOKEN_SECRET`: paste a long random value, for example from `python -c "import secrets;print(secrets.token_urlsafe(48))"`.

`wrangler deploy` prints the worker URL, for example `https://ptcgl-monitor-ai.<account>.workers.dev`. Put that URL plus `/v1` in `edition.py`:

```python
HOSTED_AI_URL = "https://ptcgl-monitor-ai.<account>.workers.dev/v1"
```

The URL is public and safe to commit. It only accepts signed tokens.

Check it:

```bash
curl -s -X POST https://ptcgl-monitor-ai.<account>.workers.dev/v1/register
```

This returns `{"token":"v1...."}`.

## Build both editions

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File installer\build_installer.ps1 -Edition ai
powershell -NoProfile -ExecutionPolicy Bypass -File installer\build_installer.ps1 -Edition free
```

| Edition | Installer | Notes |
|---|---|---|
| AI | `PokemonTCGLiveMonitor-<v>-Setup.exe` | Refuses to build without `HOSTED_AI_URL`. |
| Free | `PokemonTCGLiveMonitor-<v>-Free-Setup.exe` | No built-in AI. |

Attach both to the release. The in-app updater picks the one matching its edition.

## Operate

- **Logs:** `npx wrangler tail` (no prompts or keys are logged).
- **Change limits:** edit `[vars]` in `wrangler.toml`, then run `npx wrangler deploy`.
- **Rotate the OpenAI key:** run `npx wrangler secret put OPENAI_API_KEY`. No app update is needed.
- **Tests:** `node --test test/logic.test.mjs` covers tokens, request filtering, limits and cost. The app side is covered in `test_ai_provider.py`, which runs against a mock proxy.
