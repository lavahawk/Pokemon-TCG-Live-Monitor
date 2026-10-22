# Pokemon TCG Live Monitor v2.11

Your HUD buddy got a lot more personality this time, plus new sounds, smoother deck links and a few things that just look better.

## Install
Grab **`PokemonTCGLiveMonitor-2.11.0-Free-Setup.exe`** below and run it.

- It ships with its own Python and Tesseract, so there's nothing else to download.
- No admin rights needed. If you're on any 2.x version, just install over it; your battles and settings stay put.
- SmartScreen will probably complain since the installer isn't signed. Click **More info → Run anyway**. The `.sha256` is there if you want to check the file.
- Windows 10 or 11, 64-bit.

## HUD buddy
- **Wins and losses feel different every time.** Six ways to celebrate (hops, a victory lap, confetti, fireworks, a spin with music notes, a heart shower) and six ways to be sad about it (moping off for a nap, a sigh under its own rain cloud, sulking at the wall, kicking a pebble, tears, a grumpy fit). It never does the same one twice in a row. Win streaks get a "3 in a row!", and breaking a losing streak gets a very relieved "Finally!".
- **It remembers how things are going.** A rough losing run makes it sad, and a long one makes it properly down: it walks slower, naps more and sometimes sits facing the wall. Wins, pets, treats and time cheer it back up.
- **More berries.** Oran isn't everything anymore. New ones: **Lum** (cures the gloom), **Colbur** (the dark one, makes it sleepy) and **Enigma** (a surprise). The rarer berries sparkle, smoke or shimmer in a way that hints at what they do.
- **Little moments.** Now and then: looking around, a sneeze, chasing a butterfly, tripping over nothing, humming, grumbling, and stargazing late at night.
- **The Pokéball in the HUD is proper pixel art now,** sharp at any Windows scaling, lined up with the text. Every so often after a game it gives a little wobble, like a ball with something inside. (Haven't met your buddy yet? Double-click it.)
- It no longer slips behind the left edge of the HUD.

## Sounds
- The two-note sound is the new default and is now called **Ding**. The old ding recording is now called **Chime**. If you picked one before, you keep it.
- Two new ones: **Coin drop** and **Bubble pop**.

## Deck links
- Copied a link to a deck you already have (same cards, same name)? Nothing pops up. Opening one in the browser just shows a short "Already in your decklists" note.
- Links still work if the website is down: the whole deck lives in the link, so copying one while the game is open opens the import box.
- Links you post in Discord and other apps now show a proper preview with a banner, instead of a plain "shared deck".

## Fixes
- Resizing the dashboard from its top or left edge no longer flashes. You'll see an outline of the new size, and it resizes when you let go.
- A battle that ended while your buddy was resting in the ball was counted twice in its mood.
