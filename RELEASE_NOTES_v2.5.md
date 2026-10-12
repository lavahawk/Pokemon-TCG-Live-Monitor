# Pokemon TCG Live Monitor v2.5

A statistics and dashboard release: a new interactive dashboard, deck pin / star / ignore, and a **Deck Score** that compares your decks with the whole meta while accounting for sample size, event type and opponent strength. Plus a lighter, more reliable background monitor.

## Install
Download **`PokemonTCGLiveMonitor-2.5.0-Setup.exe`** below and run it. That's all.

- **Everything is included:** its own Python runtime with every package, plus Tesseract OCR. Nothing is downloaded during setup.
- **No admin rights.** It installs for your Windows account only. Upgrading over v2.x keeps your battle history and settings.
- Windows SmartScreen may warn because the installer isn't code-signed: **More info → Run anyway**. Check the file against the attached `.sha256` if you like.
- Requires Windows 10 or 11, 64-bit.

## Dashboard
- **New interactive charts** for rank and win rate.
  - Hover for details, drag to zoom, double-click to reset.
  - Axis labels never overlap. Breaks between sessions no longer squash the data.
  - Range buttons: **Auto** (your current climb / recent games), Session, 1W, 1M, 3M, All.
- **Win rate with a confidence band** that narrows as you play more games. A dashed line shows your last N games, and a strip shows each result.
- **Headline cards:** current rank, win rate, today / last session (record and ± points), last 10 (form and streak).
- Clearer wording everywhere: every estimate reads "72%" with its range "54–88%". The formula behind every custom number is shown on hover, with your real numbers plugged in.

## Decks
- **Pin** a deck to the front of the tabs, **Star** it to include it in the Meta analysis, **Ignore** it to leave fun or test decks out of the dashboard and overall stats.
- Deck pages show the **Meta Score** (with archetype) and your **Own games score**.

## Meta tab and the Deck Score
- **Score** = expected win rate against today's meta. Each opponent is weighted by how common it is, from a hierarchical Bayesian model fitted to all Limitless data:
  - **Sample size:** small samples are pulled toward what's typical, so a deck can't top the list on a handful of games.
  - **Honest sample sizes:** event weights no longer invent games, and one player's rounds count as related games.
  - **Opponent strength:** your ladder games count less than tournament games, and their win rate is adjusted for easier opponents. In-person Day 2 / Worlds results inform deck strength.
  - **Rank:** firm once the weighted sample is precise enough. Otherwise a predicted rank with a 90% range.
- **Your starred decks** stand out in the list (highlighted row, YOUR DECK badge). Score them "with archetype" or "on own games only".
- **Data filters:** All sources / Online / In-person / Japan, and a **Custom weights** on/off toggle.
- In-person **Converts** is now sample-size adjusted.
- New **Advanced → Preferences → Opponent strength** settings.

## Background monitor
- **Much lighter while idle:** the check for Pokemon TCG Live used about a third of a CPU core on PCs with many processes; it now uses about 0.3%.
- **No dialog at sign-in:** on a fresh install, the hidden monitor asks for your username when the game first opens, not at Windows sign-in.
- **The installer no longer removes an auto-start entry that belongs to another copy** (e.g. a second install folder).

## Also since v2.4.0
- Auto-export verified in real games: the button must read "BATTLE LOG" before it's clicked, in-battle detection uses the settings gear, and the Continue blocker appears in ~0.05 s.
- Master-league rank OCR (4-digit points), faster dashboard loading, exact Bayesian statistics with tie rules and weighted personal records.
- Unified meta sheet: Limitless online + in-person + Japan City Leagues, with Preferences weights. New In Person tab (event finder, printable decklist).

Full engineering notes: `DevVault/` (open it as an Obsidian vault). Start with `04 Dev/Handoff 2026-10-12.md`.
