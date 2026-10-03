#!/usr/bin/env bash
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
APP="$HOME/.local/share/colorchooser"

python3 -c "import gi; gi.require_version('Gtk','3.0')" 2>/dev/null || {
  echo "Missing deps. Run: sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0"; exit 1; }

mkdir -p "$APP" "$HOME/.local/bin" "$HOME/.local/share/applications"
cp "$DIR/colorchooser.py" "$APP/colorchooser.py"
chmod +x "$APP/colorchooser.py"
ln -sf "$APP/colorchooser.py" "$HOME/.local/bin/colorchooser"

cat > "$HOME/.local/share/applications/colorchooser.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Color Chooser
Comment=Pick, convert and organize colors
Exec=$HOME/.local/bin/colorchooser
Icon=applications-graphics
Categories=Graphics;Utility;
Actions=Pick;

[Desktop Action Pick]
Name=Pick from screen
Exec=$HOME/.local/bin/colorchooser --pick
EOF

echo "Installed. Run: colorchooser   (or colorchooser --pick)"
