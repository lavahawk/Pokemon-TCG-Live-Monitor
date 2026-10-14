---
tags: [findings, security, privacy]
updated: 2026-10-11
---
# Security and Privacy Review

Threat model: a single-user desktop tool. The interesting attackers are (a) web content loaded in the embedded browser (Limitless pages, which can include user-generated content such as chat), (b) anyone who gets the app folder (shared zip, backup, git push), and (c) the supply chain for installers. Severity reflects that model.

| ID | Sev | Status | Issue |
|---|---|---|---|
| SEC-01 | High (privacy) | fixed (v2.4) | Any copied text of 120+ characters that isn't a battle log is saved to `Logs/unmatched_*.txt` while the game is running |
| SEC-02 | Med | fixed (post-2.6.0, DPAPI) | OpenAI API key stored in plaintext `.openai_key` in the app folder |
| SEC-03 | Med | fixed (v2.4) | Embedded Limitless pages get `JavascriptCanAccessClipboard` (remote JS can read the system clipboard) |
| SEC-04 | Med | fixed (v2.4) | `webbrowser.open()` on URLs scraped from page DOM with no scheme/host allowlist |
| SEC-05 | Low | fixed (v2.4) | `activeMatchUrl` from any `a[href*="/match/"]` loaded into the logged-in profile without a host check |
| SEC-06 | Med | fixed (v2.4) | Tesseract installer downloaded and executed (often as admin) with no hash/signature check; predictable `%TEMP%` path |
| SEC-07 | Low | fixed (v2.4) | `update_battle_record` builds SQL column names from dict keys (latent SQL injection) |
| SEC-08 | Low | fixed (v2.4) | Sprite cache filename only strips `/`; `\` / `..` from remote icon names → path traversal on Windows |
| SEC-09 | Info | fixed (post-2.6.0) | Third-party data sharing isn't disclosed in the UI (full battle logs incl. opponent names → OpenAI, ptcglreplay) |
| SEC-10 | Info | ok | Limitless session cookies live in `.limitless_web_profile/` (gitignored; make sure release builders never zip the folder wholesale) |
| SEC-11 | Med | fixed (v2.4) | Install bat registers the monitor as a scheduled task with `/rl highest`, so the whole app (incl. WebEngine browsing) runs elevated at every logon |

## SEC-01: Clipboard forensics dump
`TCGLiveMonitor.monitor_clipboard` L373–398: when clipboard content is ≥120 chars and not a battle log, it writes the full content to `Logs/unmatched_<ts>.txt` and logs the first 80 chars to `autoclicker.log`. The loop also prints a 60-char preview of every clipboard change to the console. So passwords, private messages and documents copied while PTCGL is open end up on disk in plaintext.
**Fix:** only dump text that partially looks like a log (e.g. has a "Turn"/"Setup" marker), put it behind a debug setting, cap the size, and never log previews.

## SEC-02: API key at rest
`app_settings.save_api_key` writes `.openai_key` in plain text; `INSTALL_COMPLETE` does `echo !api_key! > .openai_key` (also leaves a trailing space). It's gitignored, but it sits in `Downloads\BattleLogImport` and gets copied with the folder. **Fix:** Windows Credential Manager via `keyring` (DPAPI-backed), with a migration that reads the old file once and deletes it. **Ask:** confirm with `git log --all -- .openai_key` that it was never committed.

## SEC-03: Clipboard access for remote pages
`StatsUI.py` L805–825 and L849–852 set `JavascriptCanAccessClipboard` and `LocalContentCanAccessClipboard` on every page of the Limitless profile, so any script running on those pages (or on pages they navigate to) can read the clipboard silently. The clipboard here routinely holds battle logs and whatever else the user copies. **Fix:** remove it; if "click to copy" matters, allow it only with `JavascriptCanPaste` off and a host check.

## SEC-04 / SEC-05: Untrusted URLs
`_handle_chat_probe_result` → `_open_decklist_image_tab(url)` → `webbrowser.open(url)`. The URL comes from the DOM, including the fallback "any `a[href*=.png]` on the page", which could be a link inside match chat. On Windows `webbrowser.open` ends in `os.startfile`, so `file://`, UNC (`\\host\share`, which leaks NTLM) and custom protocol handlers are all reachable. `activeMatchUrl` is similarly trusted. **Fix:** allow only `https://` on `*.limitlesstcg.com` (and known image CDNs).

## SEC-06: Installer supply chain
`setup_install.py` downloads two Tesseract URLs (the second, `5.5.3.20260724`, needs verifying that it exists), saves to `%TEMP%\tesseract-setup.exe` and runs it; the bat does the same as admin with `5.5.0`. There's no SHA-256 pin. **Fix:** pin hashes, download to a random temp dir, verify the Authenticode signature.

## SEC-07: Dynamic SQL identifiers
`BattleDatabase.update_battle_record` L182 `f"{column} = ?"` comes from `updates` keys. Today the only caller maps a fixed `field_map`, so it's safe, but whitelist the columns in the DB layer anyway.

## SEC-08: Sprite path
`_sprite_cache_path` normalizes spaces to `-` and replaces `/` only. Names come from the Limitless/TrainerHill APIs and the user's "online sprite" search box. **Fix:** `re.sub(r'[^a-z0-9-]', '', name)`.

## SEC-09: Data disclosure
- Every battle log (both usernames, full play log) goes to OpenAI when a key is set; Japan "AI translate" also uses it.
- Replay uploads the log to ptcglreplay.com (in the embedded page).
- Limitless chat is captured to `.chat_capture.json` and stored per battle (`battles.chat_log`).
Recommend a one-line notice in Settings, plus an option to strip opponent names before sending to AI.

## SEC-11: Elevated runtime
`INSTALL_COMPLETE_v2.3.bat` step 9 → `schtasks /create … /rl highest`. The monitor then launches the overlay, which hosts QtWebEngine browsing the web, all as admin. `startup_utils.add_task` does the same as a fallback. **Fix:** use the HKCU Run key only (no elevation needed); that's already the primary path in `startup_utils`.

## Good practices already present
Parameterized SQL everywhere else; `.gitignore` covers keys, DB, cookies and logs; the replay profile is off-the-record and rebuilt per load; the single-instance lock is race-free on Windows.
