# Pokemon TCG Live Monitor v2.7

This one is about decklists, playing without an API key, and a dashboard window that finally behaves. There's also a pile of fixes under the hood.

## Install
Grab **`PokemonTCGLiveMonitor-2.7.0-Setup.exe`** below and run it.

- It ships with its own Python and Tesseract, so there's nothing else to download.
- No admin rights needed. If you're on any 2.x version, just install over it; your battles and settings stay put.
- SmartScreen will probably complain since the installer isn't signed. Click **More info → Run anyway**. The `.sha256` is there if you want to check the file.
- Windows 10 or 11, 64-bit.

## Decklists
Link a list to a deck (Deck page → **+ Import decklist**), then open the **Decklist ▾** menu:
- **View as picture**: your list as real card images with copy counts. Hover a card to pop it out in high resolution. Switch to **Normalized** for the Limitless ImgGen version with every card in its regular printing. Save it as a PNG or copy it.
- **Print decklist**: opens the tournament decklist sheet with your list filled in. **Save PDF** puts it in Downloads, and **Print…** opens your printer's print dialog.
- **Buy on TCGplayer** *(beta)*: opens TCGplayer Mass Entry with the exact cards from your list and adds them to your cart for you. You still optimize the cart and check out yourself.
- The import window and the other decklist windows now match the app. They're see-through like the dashboard, you can move and resize them, and **▾** shrinks them to a small pill while you're in the game. Import picks up the list the moment you export it from PTCGL.
- If you've seen all 60 cards of one of your decks over a few games, the app saves the list for you.

## No API key? Manual mode
- Battles are still logged without an OpenAI key. After each one, a card asks what you played against. The best guesses are one click away, and the search lists meta decks first with their icons and meta share.
- A small notice tells you when AI deck detection is off, with a button that takes you straight to the key setting in Advanced.
- The guesses come from a small local model: the cards your opponent revealed, the decks you actually meet on ladder, and decks only you have seen. No AI, and nothing is sent anywhere.

## Dashboard window
- Fullscreen no longer gets stuck. Restoring goes back to your normal size, even after a restart.
- Move the window from the top bar or the empty space next to the tabs, and resize it from any edge. Double-click the top bar or press **F11** to fill the screen.
- Drag the tabs to reorder them; your order is remembered.
- Deck pages have a new **Rank with this deck** chart.
- Refreshing is about 5× faster, and the browser tabs only load when you open them.

## Privacy and security
- Your OpenAI key is now stored encrypted with your Windows account, not as a plain text file. It's converted automatically.
- There's a short note on what is sent where, and an option (on by default) to hide both usernames from OpenAI.

## Fixes
- A win could be saved as a loss when your username was the end of your opponent's name.
- Opponent names, deck guesses and accented names (Flabébé) are read more reliably.
- Cards from sets whose code starts with a number (30th Celebration) were missing from decklists.
- Replay without the built-in browser now opens the site and shows you the log file to drag in, instead of failing silently.
- The HUD buddy's save file and the decklist store can't be broken by a bad write anymore.
