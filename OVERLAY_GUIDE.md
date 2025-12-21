# Modern Overlay UI - Quick Start Guide

## ✨ What is it?

A sleek, minimal overlay that sits in the corner of your screen and shows real-time Pokemon TCG Live stats!

## 🚀 How to Start

**Option 1: Double-click**
```
Start_Overlay.bat
```

**Option 2: Command line**
```bash
python OverlayUI.py
```

**Option 3: Background (no console)**
```bash
pythonw OverlayUI.py
```

## 📊 Features

### Stats Displayed
- 🎯 **Current Rank** - Your latest OCR-detected rank
- 🏆 **Max Rank** - Your highest rank achieved
- 🃏 **Current Deck** - The deck you're playing
- 📊 **Session Stats** - Win/Loss ratio with percentage
- 📝 **Logs Count** - Total battle logs saved

### Controls
- **Drag** - Click and hold title bar to reposition
- **[−] Button** - Minimize/Expand stats
- **[×] Button** - Hide overlay
- **System Tray** - Double-click to show/hide

### Notifications
- 🔔 New battle detected alert
- Real-time stats updates every 5 seconds
- Automatic refresh when battles complete

## 🎨 Design

**Theme**: Modern dark with cyan accents
**Position**: Top-right corner by default
**Size**: Compact 260px width
**Opacity**: Semi-transparent (92%)
**Always on Top**: Yes (won't be hidden by other windows)

## ⚙️ Customization

The overlay is highly customizable in the code:

**Position** (line ~123):
```python
# Change to top-left, bottom-right, etc.
x = screen.width() - self.width() - margin  # Right
y = margin  # Top
```

**Colors** (line ~73-124):
```python
# Main accent color
border: 2px solid #00d4ff;  # Cyan

# Background
background-color: rgba(26, 26, 26, 235);  # Dark
```

**Refresh Rate** (line ~32):
```python
self.refresh_timer.start(5000)  # 5 seconds
```

## 🔗 Integration with TCG Live Monitor

The overlay works seamlessly with your existing workflow:

1. TCGLiveMonitor.py detects battles → saves logs
2. AIParseBattleLog.py analyzes → saves to Excel
3. Wait for main menu → OCR detects rank/deck
4. **Overlay auto-updates** with new stats! 🎉

## 📱 System Tray Menu

Right-click the tray icon:
- **Show Overlay** - Make overlay visible
- **Hide Overlay** - Hide overlay
- **Quit** - Exit application

## 🎯 Visual Feedback

**Current Rank = Max Rank?**
→ Rank shows in green (you're at your peak!)

**New Battle Detected?**
→ Notification toast appears

**Stats Updated?**
→ Overlay refreshes automatically

## 🛠️ Troubleshooting

**Overlay doesn't appear?**
→ Check system tray, double-click icon

**Stats show "--"?**
→ No data files yet, play a battle!

**Wrong position?**
→ Drag it wherever you want!

**Can't see overlay?**
→ Check if it's hidden behind fullscreen game
→ Try Alt+Tab or double-click tray icon

**Stats not updating?**
→ Make sure TCGLiveMonitor.py is running
→ Check that .last_rank, .last_deck files exist

## 🔮 Future Features (Coming Soon)

- [ ] Hotkey to toggle (Ctrl+Alt+M)
- [ ] Click-through mode
- [ ] Multiple theme options
- [ ] Attach to game window
- [ ] Charts/graphs
- [ ] Settings panel
- [ ] Log viewer
- [ ] Session history

## 💡 Tips

1. **Keep it visible**: Place where it won't block game UI
2. **Minimize when not needed**: Click [−] to collapse
3. **Check after battles**: See your stats update in real-time!
4. **Track your progress**: Watch your max rank climb!

## 🎮 Perfect Workflow

```
1. Start OverlayUI.py (overlay appears)
2. Start TCGLiveMonitor.py (monitor running)
3. Play Pokemon TCG Live
4. Copy battle log after match
5. Return to main menu
6. Watch overlay update automatically! ✨
```

---

**Enjoy your modern TCG Live monitoring experience!** 🎉
