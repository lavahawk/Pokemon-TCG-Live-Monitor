# AI proxy (built-in AI for the AI edition)

The app never contains the OpenAI key. Any key shipped inside a desktop app can be pulled out of it, whether it is obfuscated, encrypted or compiled, because the app must decrypt it to use it. So the key lives here, in a Cloudflare Worker, stored as an encrypted secret. The app talks to the worker over HTTPS.

```
app ──HTTPS (TLS 1.2+, cert verified)──> Worker ──HTTPS──> OpenAI
     Bearer: per-install token             holds OPENAI_API_KEY (secret)
```

## What protects the key and the bill

- **Key:** the key is only a Worker secret. It is never sent to the app, never logged, and OpenAI error bodies are not passed back.
- **Install token:** on first use the app gets a per-install token, `v1.<id>.<HMAC>`, signed with `TOKEN_SECRET`. The app keeps it DPAPI-encrypted in `.ai_install.dpapi`. Rotating `TOKEN_SECRET` revokes every token, and apps re-register on their own.
- **Battle logs only:** the app never sends a prompt. `POST /v1/parse` takes the battle log plus a few typed fields (deck names, card evidence, username, model). The worker:
  - checks the log is a Pokémon TCG Live log (opening lines, at least 80% of lines name a player or are detail lines, line and size caps, no control characters or `<<<` markers); every saved real log passes, prose does not
  - builds the prompt itself from a fixed template (`src/prompt.js`, kept identical to the app's by a test), with the log inserted last and marked as data
  - returns only five short typed fields (deck names cut to 60 characters, result, confidence, 3 candidates); everything else the model wrote is dropped
  - caps `max_completion_tokens`, forces JSON mode and `store: false`

  So a stolen token cannot run other prompts, and a request smuggled into a "log" gets back at most a few deck-name-sized strings.
- **Limits:** enforced by Durable Objects, so the counters are exact.

  | Scope | Limit |
  |---|---|
  | Per install | $2.50 a month, 40 games a day on the main model then the light model, 150 games a day hard stop, 6 a minute |
  | All installs | $10 a day, $150 a month |
  | Registrations | 5 new installs per IP per day |

- **Kill switch:** set `AI_ENABLED = "false"` and redeploy. Every app falls back to manual mode with no errors.
- **Spend limit at OpenAI:** set a monthly budget on the OpenAI project too, and use a project key limited to the three models.

**Known limit (anonymous installs):** someone could script registrations from many IPs. The global caps bound the worst case; `/v1/register` is the single place to add a stronger check later.

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
