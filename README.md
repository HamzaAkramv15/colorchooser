# Color Chooser

A dark-purple GTK3 color picker and organizer for **Ubuntu Unity** (X11). Pick a color from anywhere on screen, see it in every format you might need, and keep the ones you like in a searchable library with palettes.

## Features

- **Screen picker**: freezes the screen under a magnifier loupe. Click or Enter picks, Esc or right-click cancels, scroll zooms, arrow keys nudge by 1px.
- **Editor**: saturation/value square, hue and alpha sliders, and a hex field that accepts `#RGB`, `#RRGGBB` and `#RRGGBBAA`.
- **9 copyable formats**: HEX, RGB, HSL, HSV, CMYK, OKLCH, plus ready-to-paste snippets for Flutter (`Color(0xFF6B4EFF)`), Qt (`QColor`) and GTK (`@define-color`). Alpha is included when the color is translucent.
- **Harmonies, shades and tints**: five harmony swatches and nine lightness steps, each one click away from becoming the current color.
- **Contrast check**: WCAG ratio against white and dark text with an AAA / AA / Large only / Fail badge, and an **Adjust to reach AA** button.
- **Library**: save, rename, star favorites, search (`Ctrl+F`), and browse All Colors, Recent and Favorites.
- **Palettes**: add colors to named palettes, or generate a 7-color palette from the current color. Right-click a palette to **copy it as CSS variables**, **export it as a GIMP palette (`.gpl`)** or delete it.
- **Undo / redo** for color changes.

## Install

```bash
git clone https://github.com/HamzaAkramv15/colorchooser.git
cd colorchooser
./install.sh
```

Installs per-user into `~/.local`: the script, a `colorchooser` launcher in `~/.local/bin`, and a `.desktop` entry with a **Pick from screen** quicklist action.

Dependencies: `python3-gi python3-gi-cairo gir1.2-gtk-3.0`. Optional: `libnotify-bin` for the "Color copied" notification.

## Use

```bash
colorchooser                 # open the window (or raise the running one)
colorchooser --pick          # pick from screen; copies + saves, window stays hidden
colorchooser --hex 6B4EFF    # open with a color (6 digits, or 8 with alpha)
```

`--pick` is meant for a global shortcut: the color is copied in your chosen format (HEX by default, changeable in the window), saved to your library, and a notification confirms it. Running it again talks to the already-running instance. After a hotkey pick with no window open, the app stays alive for 5 minutes so the clipboard survives, then quits.

| Shortcut | Action |
| --- | --- |
| `Ctrl+Shift+C` | Pick from screen |
| `Ctrl+S` | Save current color |
| `Ctrl+F` | Search |
| `Ctrl+Z` / `Ctrl+Y` | Undo / redo |

Bind `colorchooser --pick` in **System Settings > Keyboard > Shortcuts > Custom** to use it from anywhere.

## Data

- Colors and palettes: `~/.local/share/colorchooser/colors.json`
- Settings: `~/.config/colorchooser/settings.json`

## Uninstall

There is no uninstall script. To remove it:

```bash
rm -rf ~/.local/share/colorchooser ~/.local/bin/colorchooser ~/.local/share/applications/colorchooser.desktop
rm -rf ~/.config/colorchooser   # optional: also delete settings
```
