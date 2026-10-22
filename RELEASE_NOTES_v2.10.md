# Pokemon TCG Live Monitor v2.10

Sharing decks got a lot smoother this time: one button to share, a nicer page for your friends, and an import that feels like part of the app instead of a script clicking around.

## Install
Grab **`PokemonTCGLiveMonitor-2.10.0-Free-Setup.exe`** below and run it.

- It ships with its own Python and Tesseract, so there's nothing else to download.
- No admin rights needed. If you're on any 2.x version, just install over it; your battles and settings stay put.
- SmartScreen will probably complain since the installer isn't signed. Click **More info → Run anyway**. The `.sha256` is there if you want to check the file.
- Windows 10 or 11, 64-bit.

## Share in one click
- Every deck page with a list now has a **Share** button where Picture used to be. Click it and the link is on your clipboard; the button says **Copied!** so you know it worked. (The picture is still in the Decklist menu.)
- Hover tips stay out of the way for a moment after you share, so nothing pops up over the confirmation.

## A better page for the people you send it to
- The link opens the app straight away if they have it installed, in any browser.
- Click any card to see the big scan, with a link to the card on Limitless.
- A new animated logo, and the list types in at a speed you can actually watch.

## Importing a shared deck
- The import box is simpler: the deck's name, **Add it to Pokémon TCG Live** and **Add it to PTCGL Monitor**. Untick either one if you only want the deck in one place.
- The deck goes into the game under the name in the box.
- The whole thing fades from step to step instead of jumping: the box steps aside, the game dims with a progress bar that moves as each step finishes, and the box comes back telling you where the deck ended up.
- Adding it to the monitor also links the list to that deck, so its deck page shows the list as soon as you play it.

## Fixes
- Deck pictures (Your prints / Normalized) looked blurry on screens with Windows scaling above 100%. They're sharp now. Saving and copying were already fine.
