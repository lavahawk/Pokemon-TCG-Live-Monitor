# Pokemon TCG Live Monitor v2.6

Smarter opponent-deck detection, a deck page you can click through, decklists linked to your decks, a cleaner Meta tab, an ad blocker for the built-in browser tabs, and a hidden pixel buddy for your HUD.

## Install
Download **`PokemonTCGLiveMonitor-2.6.0-Setup.exe`** below and run it. That's all.

- **Everything is included:** its own Python runtime with every package, plus Tesseract OCR. Nothing is downloaded during setup.
- **No admin rights.** It installs for your Windows account only. Upgrading over v2.x keeps your battle history and settings.
- Windows SmartScreen may warn because the installer isn't code-signed: **More info → Run anyway**. Check the file against the attached `.sha256` if you like.
- Requires Windows 10 or 11, 64-bit.

## Opponent deck
- **Top 3 choices after each battle:** the overlay card shows the three most likely decks with icons and percentages. One click saves the right one.
- **Real confidence:** the number now means "how sure are we about the opponent's deck". It used to read ~90 for nearly every game. Below 50% the card turns amber, asks "Which deck was it?", and waits for your answer.
- **Read from the cards they played:** copies seen are compared against ~95,000 public decklists, and popularity breaks close calls. Local mode uses this too.

## Deck page
- **Clickable cards:**
  - **Meta Score** and **Score · your games** (now shown with ±) open the Meta tab on your deck's row and highlight it.
  - **Meta faced** jumps to the Matchups section.
  - Each **Last 10** square jumps to that game.
- **Per-game buttons:** Replay, Cards played (every card both players showed), Deck archetype.
- **Decklist:** import or link the deck's PTCGL export. It's picked up from your clipboard automatically. That unlocks:
  - card suggestions: what most lists play that yours doesn't
  - Meta → Cards comparison
  - TrainerHill Deck Diff, Card Usage and Deck Profile

## Meta tab
- Cleaner:
  - The status line is one short line; details are on hover.
  - The legend moved to the Sources heading.
  - No more ⚖ icons. The weights note only shows on affected columns, and only when custom weights are on.
  - Cell hovers are short. The formulas live on the column headings (hover **Score**).
- **Cards view:** archetype card usage from public decklists, compared against your own list.
- **Japan Data** is rebuilt on Limitless City Leagues.

## Settings and quality of life
- **Import sound:** on/off, 6 sounds, volume, preview (Advanced → Preferences · Sound).
- **Ad and tracker blocking** in the built-in browser tabs (Limitless, TrainerHill, Replay, PokeData, In Person). It's lightweight, has an editable list, and is on by default.
- **Battle database editor:** fixed layout, Replay / Log / Delete buttons, last 50 games, refreshes by itself.
- **Steadier auto-export clicks:** the cursor is held on the button during the click, so moving the mouse can't make it miss.

## Psst
Double-click the little Pokéball on the overlay.

## Also since v2.5.0
- Meta data covers the whole format: 850+ online events, in-person results and Japanese City Leagues, plus an optional Limitless API key (Advanced → Meta Data).
- The deck-page win-rate chart is interactive. The dashboard win-rate chart has a deck filter.

Full engineering notes: `DevVault/` (open it as an Obsidian vault). Start with `00 Start Here.md`.

Pixel sprites for the HUD buddy: PMD Sprite Repository (sprites.pmdcollab.org), CC BY-NC 4.0. See `pet_sprites/CREDITS.txt`.
