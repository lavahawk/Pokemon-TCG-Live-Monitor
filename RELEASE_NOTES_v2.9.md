# Pokemon TCG Live Monitor v2.9

This one is about sharing decks, a calmer interface, and choosing how the app names your opponent's deck.

## Install
Grab **`PokemonTCGLiveMonitor-2.9.0-Free-Setup.exe`** below and run it.

- It ships with its own Python and Tesseract, so there's nothing else to download.
- No admin rights needed. If you're on any 2.x version, just install over it; your battles and settings stay put.
- SmartScreen will probably complain since the installer isn't signed. Click **More info → Run anyway**. The `.sha256` is there if you want to check the file.
- Windows 10 or 11, 64-bit.

## Share a deck with one link
- Deck page → **Decklist ▾ → Share link** copies a short link that holds the whole list. Nothing is uploaded: the deck lives inside the link.
- Anyone with the app who clicks it gets a small box with the deck's name. **Import** saves it to their decklists and, if Pokémon TCG Live is open, builds it in the game for them: Decks → Create a deck → Import using the **rarest prints they own** → names it. Press Esc to stop at any time.
- Anyone without the app gets a simple page with the list, the card images, a copy of the list on their clipboard ready for PTCGL's Import, and a button to open it in Limitless's image tool.
- Copied a link from a chat while the game is open? The import box opens by itself. You can also paste a link into the decklist import window.

## A calmer interface
- Hover tips are now one or two short lines. Right-click a tip (or hold Shift) to open the details, and right-click again to pin it while you read. The same works on chart points.
- Most of the small grey explanations are gone or replaced with visuals: a reset arrow next to changed weights, a curve for how ladder games gain weight with Elo, a striped range bar when a deck has few games, and a pencil on battle cells you can edit.
- **Themes**: Advanced → Preferences · Appearance has Legacy, Graphite, Obsidian and Harbor. Picking one restarts the app by itself, and there's a **Restart app** button.

## Opponent deck detection
- Choose how decks are named in Advanced: your OpenAI key, a local or OpenAI-compatible model (Ollama, LM Studio, OpenRouter, Groq presets), or Off (local guesses only).
- Local mode explains itself once at startup and never on top of the Reset? prompt, and the deck card no longer flickers when you hover it.

## Stats
- Data weights make more sense: Master Ball and Arceus are one weight up to 1400 Elo, and above that ladder games count more and more until 1800, where they count like Limitless tournament games.
- Confidence labels come from the real 90% range, so they settle after about 30 games.

## Under the hood
- Updates now always verify the download's checksum before installing.
- API keys entered in the installer are stored encrypted right away.
