# League Pokeball Icons

## Elo Ranges & Icons

The overlay now displays a unique 8-bit pokeball icon based on your current Elo rating:

| League | Elo Range | Ball Type | Colors |
|--------|-----------|-----------|---------|
| **Nest League** | 0-29 | Nest Ball | Green/Yellow |
| **Quick League** | 30-109 | Quick Ball | Light Blue |
| **Poke League** | 110-229 | Poke Ball | Red/White |
| **Great League** | 230-389 | Great Ball | Dark Blue |
| **Ultra League** | 390-549 | Ultra Ball | Yellow/Black |
| **Master League** | 550+ | Master Ball | Purple |

## Display Format

The overlay now shows:
```
[🔴] Elo:76 | Max:82 | 5-2
```

The pokeball icon changes color based on your current Elo tier:
- **Nest Ball** (🟢): Green for new players (0-29)
- **Quick Ball** (🔵): Light blue for beginners (30-109)
- **Poke Ball** (🔴): Classic red for intermediate (110-229)
- **Great Ball** (🔵): Dark blue for advanced (230-389)
- **Ultra Ball** (🟡): Yellow for expert (390-549)
- **Master Ball** (🟣): Purple for masters (550+)

## Technical Details

- Icons are 12x12 pixels
- 8-bit pixel art style (no anti-aliasing)
- Generated programmatically with QPainter
- Updates automatically when Elo changes
- Each ball has authentic coloring matching Pokemon games

The icon provides instant visual feedback of your current league tier!
