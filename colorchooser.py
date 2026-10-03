#!/usr/bin/env python3
"""Color Chooser v2 - GTK3 color picker for Ubuntu Unity (X11).

  colorchooser                 open the window (or raise the running one)
  colorchooser --pick          pick from screen; copies + saves, window stays hidden
  colorchooser --hex 6B4EFF    open with a color (6 or 8 digits, 8 = with alpha)

Data:     ~/.local/share/colorchooser/colors.json
Settings: ~/.config/colorchooser/settings.json
"""
import argparse, colorsys, json, math, os, re, subprocess, time
import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gtk, Gdk, Gio, GLib
import cairo

DATA = os.path.expanduser("~/.local/share/colorchooser/colors.json")
CONF = os.path.expanduser("~/.config/colorchooser/settings.json")
DARK = (21, 16, 31)
TGT = [Gtk.TargetEntry.new("text/plain", 0, 0)]
FORMATS = ["HEX", "RGB", "HSL", "HSV", "CMYK", "OKLCH", "Flutter", "Qt", "GTK"]

CSS = b"""
window, .root { background-color:#17121f; color:#ece8f5; font-family:Ubuntu,Cantarell,sans-serif; }
headerbar { background-image:none; background-color:#17121f; border-bottom:1px solid #2a2338; box-shadow:none; color:#ece8f5; }
.side { background-color:#1a1524; border-right:1px solid #2a2338; }
.mid  { background-color:#1d1828; border-right:1px solid #2a2338; }
list, row { background-color:transparent; }
row.nav { padding:9px 10px; margin:1px 8px; border-radius:9px; }
row.item { padding:8px 8px; margin:1px 8px; border-radius:10px; }
row:selected { background-image:linear-gradient(90deg,#5a3fc4,#4a3796); color:#fff; }
.dim { color:#8e86a3; } row:selected .dim { color:#d9d0ff; }
.mono { font-family:'Ubuntu Mono','DejaVu Sans Mono',monospace; font-size:15px; }
entry.title { background-color:transparent; border-color:transparent; font-size:24px; font-weight:500; padding:0 4px; }
entry.title:focus { border-color:#7a55f0; background-color:#231d31; }
entry { background-color:#231d31; background-image:none; border:1px solid #2a2338; border-radius:9px; color:#ece8f5; padding:7px 10px; min-height:0; box-shadow:none; }
button { background-image:none; background-color:#231d31; border:1px solid #2a2338; border-radius:9px; color:#ece8f5; box-shadow:none; text-shadow:none; padding:7px 12px; }
button:hover { border-color:#7a55f0; }
button.primary { background-image:linear-gradient(90deg,#6a48dd,#5a3fc4); border-color:transparent; }
button.fav { color:#f5b82e; }
.sec { color:#cfc8e2; font-weight:500; }
.tagline { color:#8e86a3; }
scrolledwindow, viewport { background-color:transparent; }
menu, .menu, popover { background-color:#231d31; color:#ece8f5; border:1px solid #2a2338; }
"""


# ---------- color helpers ----------
def parse_hex(s):
    """'#RGB', '#RRGGBB', '#RRGGBBAA' -> ((r,g,b), alpha) or None."""
    s = s.strip().lstrip("#")
    if len(s) in (3, 4): s = "".join(c * 2 for c in s)
    if len(s) not in (6, 8): return None
    try: v = [int(s[i:i + 2], 16) for i in range(0, len(s), 2)]
    except ValueError: return None
    return tuple(v[:3]), (v[3] / 255 if len(v) == 4 else 1.0)

def to_hex(rgb, a=1.0): return "#%02X%02X%02X" % tuple(rgb) + ("%02X" % round(a * 255) if a < 1 else "")
def hsv2rgb(h, s, v): return tuple(round(c * 255) for c in colorsys.hsv_to_rgb(h, s, v))
def hls2rgb(h, l, s): return tuple(round(c * 255) for c in colorsys.hls_to_rgb(h, l, s))

def lum(rgb):
    a = [(c / 255 / 12.92) if c / 255 <= .03928 else ((c / 255 + .055) / 1.055) ** 2.4 for c in rgb]
    return .2126 * a[0] + .7152 * a[1] + .0722 * a[2]

def contrast(a, b):
    x, y = lum(a), lum(b)
    return (max(x, y) + .05) / (min(x, y) + .05)

def badge(r): return "AAA" if r >= 7 else "AA" if r >= 4.5 else "Large only" if r >= 3 else "Fail"

def oklch(rgb):
    r, g, b = [max(0, (c / 255 / 12.92) if c / 255 <= .04045 else ((c / 255 + .055) / 1.055) ** 2.4) for c in rgb]
    l = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    m = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    s = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    L = 0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s
    A = 1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s
    B = 0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s
    return L, math.hypot(A, B), math.degrees(math.atan2(B, A)) % 360

def formats(rgb, a):
    r, g, b = rgb; al = a < 1; nrm = [c / 255 for c in rgb]
    h, l, s = colorsys.rgb_to_hls(*nrm); hv, sv, vv = colorsys.rgb_to_hsv(*nrm)
    k = 1 - max(nrm); cmy = [0, 0, 0] if k >= 1 else [(1 - c - k) / (1 - k) for c in nrm]
    L, C, H = oklch(rgb); hx = to_hex(rgb, a); a255 = round(a * 255)
    return {
        "HEX": hx,
        "RGB": "rgba(%d, %d, %d, %.2f)" % (r, g, b, a) if al else "rgb(%d, %d, %d)" % (r, g, b),
        "HSL": ("hsla(%d, %d%%, %d%%, %.2f)" if al else "hsl(%d, %d%%, %d%%)") % ((round(h * 360), round(s * 100), round(l * 100)) + ((a,) if al else ())),
        "HSV": "hsv(%d, %d%%, %d%%)" % (round(hv * 360), round(sv * 100), round(vv * 100)),
        "CMYK": "cmyk(%d%%, %d%%, %d%%, %d%%)" % (*[round(c * 100) for c in cmy], round(k * 100)),
        "OKLCH": "oklch(%.1f%% %.3f %d)" % (L * 100, C, round(H)) + ("" if not al else " / %.2f" % a),
        "Flutter": "Color(0x%02X%s)" % (a255, to_hex(rgb)[1:]),
        "Qt": ('QColor(%d, %d, %d, %d)' % (r, g, b, a255)) if al else 'QColor("%s")' % to_hex(rgb),
        "GTK": "@define-color color %s;" % (("rgba(%d, %d, %d, %.2f)" % (r, g, b, a)) if al else to_hex(rgb)),
    }

def when(ts):
    t, n = time.localtime(ts), time.localtime()
    if t[:3] == n[:3]: return time.strftime("%H:%M", t)
    if t.tm_year == n.tm_year and t.tm_yday == n.tm_yday - 1: return "Yesterday"
    return time.strftime("%b %d", t)

def tint(w, bg, fg="#fff", radius=12):
    css = ("* { background-color:%s; color:%s; border-radius:%dpx; }" % (bg, fg, radius)).encode()
    if not hasattr(w, "_tp"):
        w._tp = Gtk.CssProvider()
        w.get_style_context().add_provider(w._tp, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1)
    w._tp.load_from_data(css)

def rounded(cr, x, y, w, h, r):
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0); cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi); cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()

def checker(cr, x, y, w, h, s=8):
    cr.set_source_rgb(.30, .28, .35); cr.rectangle(x, y, w, h); cr.fill(); cr.set_source_rgb(.42, .40, .48)
    for i in range(int(w // s) + 1):
        for j in range(int(h // s) + 1):
            if (i + j) % 2: cr.rectangle(x + i * s, y + j * s, s, s)
    cr.fill()

def copy(text): Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(text, -1)

def notify(title, body):
    try: subprocess.Popen(["notify-send", "-i", "applications-graphics", title, body])
    except OSError: pass

def load_json(path, default):
    try:
        with open(path) as f: return json.load(f)
    except Exception: return default

def save_json(path, d):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f: json.dump(d, f, indent=1)


# ---------- widgets ----------
class Swatch(Gtk.DrawingArea):
    def __init__(self, w, h, r=10, on_click=None):
        super().__init__(); self.set_size_request(w, h); self.r, self.hex = r, "#6B4EFF"
        if on_click:
            self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
            self.connect("button-press-event", lambda *_: on_click(self.hex))
        self.connect("draw", self.draw)
    def set_hex(self, hx): self.hex = hx; self.queue_draw()
    def draw(self, w, cr):
        W, H = self.get_allocated_width(), self.get_allocated_height(); rgb, a = parse_hex(self.hex)
        rounded(cr, .5, .5, W - 1, H - 1, self.r); cr.save(); cr.clip()
        if a < 1: checker(cr, 0, 0, W, H, 6)
        cr.set_source_rgba(*[c / 255 for c in rgb], a); cr.paint(); cr.restore()
        rounded(cr, .5, .5, W - 1, H - 1, self.r); cr.set_source_rgba(1, 1, 1, .15); cr.stroke()

class Preview(Gtk.DrawingArea):
    def __init__(self):
        super().__init__(); self.set_size_request(150, 200); self.rgb, self.a = (107, 78, 255), 1.0; self.connect("draw", self.draw)
    def draw(self, w, cr):
        W, H = self.get_allocated_width(), self.get_allocated_height()
        rounded(cr, 0, 0, W, H, 12); cr.save(); cr.clip(); checker(cr, 0, 0, W, H)
        cr.set_source_rgba(*[c / 255 for c in self.rgb], self.a); cr.paint(); cr.restore()
        eff = tuple(self.a * c + (1 - self.a) * 100 for c in self.rgb); fg = .08 if lum(eff) > .45 else 1
        cr.set_source_rgb(fg, fg, fg)
        for i, (t, sz, wt) in enumerate((("Aa  Preview", 18, 1), ("Ubuntu Unity", 13, 0), ("Beautiful Linux", 13, 0))):
            cr.select_font_face("Ubuntu", 0, wt); cr.set_font_size(sz); tw = cr.text_extents(t)[2]
            cr.move_to((W - tw) / 2, H / 2 + (i - 1) * 28); cr.show_text(t)

class SVPicker(Gtk.DrawingArea):
    def __init__(self, on_change, on_done):
        super().__init__(); self.set_size_request(-1, 200); self.h = self.s = self.v = 1.0
        self.cb, self.done, self.drag = on_change, on_done, False
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK | Gdk.EventMask.POINTER_MOTION_MASK)
        self.connect("draw", self.draw); self.connect("button-press-event", self.press)
        self.connect("button-release-event", self.release)
        self.connect("motion-notify-event", lambda w, e: self.drag and self.move(e))
    def press(self, w, e): self.drag = True; self.move(e)
    def release(self, *_): self.drag = False; self.done()
    def move(self, e):
        W, H = self.get_allocated_width(), self.get_allocated_height()
        self.s = min(1, max(0, e.x / W)); self.v = 1 - min(1, max(0, e.y / H)); self.cb(self.s, self.v)
    def draw(self, w, cr):
        W, H = self.get_allocated_width(), self.get_allocated_height()
        rounded(cr, 0, 0, W, H, 12); cr.save(); cr.clip()
        cr.set_source_rgb(*colorsys.hsv_to_rgb(self.h, 1, 1)); cr.paint()
        g = cairo.LinearGradient(0, 0, W, 0); g.add_color_stop_rgba(0, 1, 1, 1, 1); g.add_color_stop_rgba(1, 1, 1, 1, 0)
        cr.set_source(g); cr.paint()
        g = cairo.LinearGradient(0, 0, 0, H); g.add_color_stop_rgba(0, 0, 0, 0, 0); g.add_color_stop_rgba(1, 0, 0, 0, 1)
        cr.set_source(g); cr.paint(); cr.restore()
        cr.arc(self.s * W, (1 - self.v) * H, 9, 0, 2 * math.pi); cr.set_line_width(3); cr.set_source_rgb(1, 1, 1); cr.stroke_preserve()
        cr.set_line_width(1); cr.set_source_rgba(0, 0, 0, .5); cr.stroke()

class Bar(Gtk.DrawingArea):
    """Horizontal slider. kind='hue' or 'alpha'; value v in 0..1."""
    def __init__(self, kind, on_change, on_done):
        super().__init__(); self.set_size_request(-1, 16); self.kind, self.cb, self.done, self.drag = kind, on_change, on_done, False
        self.v, self.rgb = (0.0 if kind == "hue" else 1.0), (107, 78, 255)
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK | Gdk.EventMask.POINTER_MOTION_MASK)
        self.connect("draw", self.draw); self.connect("button-press-event", self.press)
        self.connect("button-release-event", self.release)
        self.connect("motion-notify-event", lambda w, e: self.drag and self.move(e))
    def press(self, w, e): self.drag = True; self.move(e)
    def release(self, *_): self.drag = False; self.done()
    def move(self, e): self.v = min(1, max(0, e.x / self.get_allocated_width())); self.cb(self.v)
    def draw(self, w, cr):
        W, H = self.get_allocated_width(), self.get_allocated_height()
        rounded(cr, 0, 0, W, H, H / 2); cr.save(); cr.clip()
        if self.kind == "hue":
            g = cairo.LinearGradient(0, 0, W, 0)
            for i in range(7): g.add_color_stop_rgb(i / 6, *colorsys.hsv_to_rgb(i / 6, 1, 1))
            cr.set_source(g); cr.paint()
        else:
            checker(cr, 0, 0, W, H, 6); c = [x / 255 for x in self.rgb]
            g = cairo.LinearGradient(0, 0, W, 0); g.add_color_stop_rgba(0, *c, 0); g.add_color_stop_rgba(1, *c, 1); cr.set_source(g); cr.paint()
        cr.restore()
        cr.arc(self.v * (W - H) + H / 2, H / 2, H / 2 - 1, 0, 2 * math.pi); cr.set_source_rgb(1, 1, 1); cr.fill_preserve()
        cr.set_source_rgb(.09, .07, .12); cr.set_line_width(2); cr.stroke()


class ScreenPicker(Gtk.Window):
    """Freezes the screen under a grabbed popup and shows a magnifier loupe.
    Click/Enter picks - Esc/right-click cancels - scroll zooms - arrow keys nudge 1px."""
    N, ZOOMS = 11, (8, 10, 12, 16)
    def __init__(self, cb):
        super().__init__(type=Gtk.WindowType.POPUP); self.cb, self.zi, self.finished = cb, 2, False
        root = Gdk.get_default_root_window(); self.W, self.H = root.get_width(), root.get_height()
        pb = Gdk.pixbuf_get_from_window(root, 0, 0, self.W, self.H)
        self.pb, self.buf, self.rs, self.nc = pb, pb.get_pixels(), pb.get_rowstride(), pb.get_n_channels()  # cache once: get_pixels() copies
        self.seat = Gdk.Display.get_default().get_default_seat()
        _, x, y = self.seat.get_pointer().get_position(); self.pos = (x, y)
        self.set_app_paintable(True); self.set_default_size(self.W, self.H)
        self.add_events(Gdk.EventMask.POINTER_MOTION_MASK | Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.KEY_PRESS_MASK | Gdk.EventMask.SCROLL_MASK)
        self.connect("draw", self.draw); self.connect("motion-notify-event", self.motion); self.connect("button-press-event", self.click)
        self.connect("key-press-event", self.key); self.connect("scroll-event", self.scroll)
    def start(self): self.show_all(); self.move(0, 0); GLib.timeout_add(30, self.grab, 0)
    def grab(self, tries):
        cur = Gdk.Cursor.new_from_name(Gdk.Display.get_default(), "crosshair")
        st = self.seat.grab(self.get_window(), Gdk.SeatCapabilities.ALL, False, cur, None, None, None)
        if st == Gdk.GrabStatus.SUCCESS: return False
        if tries > 20: self.finish(None)
        else: GLib.timeout_add(30, self.grab, tries + 1)
        return False
    def finish(self, hx):
        if self.finished: return
        self.finished = True; self.seat.ungrab(); self.destroy(); self.cb(hx)
    def px(self, x, y):
        x, y = min(self.W - 1, max(0, x)), min(self.H - 1, max(0, y)); i = y * self.rs + x * self.nc
        return (self.buf[i], self.buf[i + 1], self.buf[i + 2])
    def motion(self, w, e): self.pos = (int(e.x), int(e.y)); self.queue_draw()
    def click(self, w, e): self.finish(to_hex(self.px(*self.pos)) if e.button == 1 else None)
    def scroll(self, w, e):
        self.zi = min(len(self.ZOOMS) - 1, max(0, self.zi + (1 if e.direction == Gdk.ScrollDirection.UP else -1))); self.queue_draw()
    def key(self, w, e):
        k = e.keyval; d = {Gdk.KEY_Left: (-1, 0), Gdk.KEY_Right: (1, 0), Gdk.KEY_Up: (0, -1), Gdk.KEY_Down: (0, 1)}.get(k)
        if k == Gdk.KEY_Escape: self.finish(None)
        elif k in (Gdk.KEY_Return, Gdk.KEY_space): self.finish(to_hex(self.px(*self.pos)))
        elif d:
            scr, x, y = self.seat.get_pointer().get_position(); self.seat.get_pointer().warp(scr, x + d[0], y + d[1])
            self.pos = (self.pos[0] + d[0], self.pos[1] + d[1]); self.queue_draw()
    def draw(self, w, cr):
        Gdk.cairo_set_source_pixbuf(cr, self.pb, 0, 0); cr.paint()
        x, y = self.pos; Z = self.ZOOMS[self.zi]; S = self.N * Z; h = self.N // 2; LW = max(S, 190)
        lx, ly = x + 24, y + 24
        if lx + LW > self.W - 8: lx = x - 24 - LW
        if ly + S + 34 > self.H - 8: ly = y - 24 - S - 34
        for i in range(self.N):
            for j in range(self.N):
                cr.set_source_rgb(*[c / 255 for c in self.px(x - h + i, y - h + j)]); cr.rectangle(lx + i * Z, ly + j * Z, Z, Z); cr.fill()
        cr.set_source_rgb(1, 1, 1); cr.set_line_width(2); cr.rectangle(lx + h * Z, ly + h * Z, Z, Z); cr.stroke()
        cr.set_source_rgba(.1, .08, .15, .95); rounded(cr, lx - 1, ly + S + 4, LW + 2, 28, 8); cr.fill()
        c = self.px(x, y); cr.set_source_rgb(*[v / 255 for v in c]); cr.arc(lx + 14, ly + S + 18, 7, 0, 2 * math.pi); cr.fill()
        cr.set_source_rgb(1, 1, 1); cr.select_font_face("Ubuntu Mono"); cr.set_font_size(15)
        cr.move_to(lx + 30, ly + S + 23); cr.show_text("%s   %d, %d, %d" % (to_hex(c), *c))


# ---------- main window ----------
class Win(Gtk.Window):
    def __init__(self, app):
        super().__init__(title="Color Chooser", application=app); self.set_default_size(1120, 760); self.app = app
        self.data = load_json(DATA, {"colors": [], "palettes": {}})
        self.conf = load_json(CONF, {"pick_copy": "HEX"})
        self.rgb, self.alpha, self.filter, self.lock = (107, 78, 255), 1.0, "all", False
        self.hist, self.hi = [], -1
        self.connect("destroy", lambda *_: app.quit()); self.connect("key-press-event", self.on_key)

        hb = Gtk.HeaderBar(show_close_button=True, title="Color Chooser"); self.set_titlebar(hb)
        for icon, d in (("edit-undo-symbolic", -1), ("edit-redo-symbolic", 1)):
            b = Gtk.Button.new_from_icon_name(icon, Gtk.IconSize.BUTTON); b.connect("clicked", lambda _, d=d: self.undo(d)); hb.pack_start(b)
        combo = Gtk.ComboBoxText()
        for f in FORMATS: combo.append_text(f)
        combo.set_active(FORMATS.index(self.conf.get("pick_copy", "HEX")) if self.conf.get("pick_copy") in FORMATS else 0)
        combo.connect("changed", self.set_pick_copy); hb.pack_end(combo); hb.pack_end(Gtk.Label(label="On pick, copy"))

        root = Gtk.Box(); root.get_style_context().add_class("root"); self.add(root)
        side = Gtk.Box(orientation=Gtk.Orientation.VERTICAL); side.set_size_request(220, -1)
        side.get_style_context().add_class("side"); root.pack_start(side, False, False, 0)
        self.nav = Gtk.ListBox(); self.nav.connect("row-selected", self.on_nav); self.nav.connect("button-press-event", self.nav_click)
        side.pack_start(self.nav, False, False, 10)
        tag = Gtk.Label(label="Pick it once,\nuse it everywhere.", justify=Gtk.Justification.CENTER)
        tag.get_style_context().add_class("tagline"); side.pack_end(tag, False, False, 20)

        mid = Gtk.Box(orientation=Gtk.Orientation.VERTICAL); mid.set_size_request(320, -1)
        mid.get_style_context().add_class("mid"); root.pack_start(mid, False, False, 0)
        bar = Gtk.Box(spacing=8, margin=12); mid.pack_start(bar, False, False, 0)
        self.search = Gtk.SearchEntry(placeholder_text="Search colors..."); self.search.connect("search-changed", lambda *_: self.refresh_list())
        bar.pack_start(self.search, True, True, 0)
        add = Gtk.Button.new_from_icon_name("list-add-symbolic", Gtk.IconSize.BUTTON); add.set_tooltip_text("Save color (Ctrl+S)")
        add.connect("clicked", lambda *_: self.save_current()); bar.pack_start(add, False, False, 0)
        sc = Gtk.ScrolledWindow(); mid.pack_start(sc, True, True, 0)
        self.lst = Gtk.ListBox(); self.lst.connect("row-selected", self.on_row); sc.add(self.lst)

        sc2 = Gtk.ScrolledWindow(); root.pack_start(sc2, True, True, 0)
        ed = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14, margin=24); sc2.add(ed)
        head = Gtk.Box(spacing=14); ed.pack_start(head, False, False, 0)
        self.big = Swatch(52, 52, 12); head.pack_start(self.big, False, False, 0)
        tb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL); head.pack_start(tb, True, True, 0)
        self.name = Gtk.Entry(has_frame=False); self.name.get_style_context().add_class("title")
        self.name.connect("activate", self.rename); self.name.connect("focus-out-event", lambda *_: self.rename()); tb.pack_start(self.name, False, False, 0)
        self.sub = Gtk.Label(xalign=0, margin_start=4); self.sub.get_style_context().add_class("dim"); tb.pack_start(self.sub, False, False, 0)
        self.favb = Gtk.Button(label="★"); self.favb.get_style_context().add_class("fav"); self.favb.connect("clicked", self.toggle_fav); head.pack_start(self.favb, False, False, 0)
        rm = Gtk.Button.new_from_icon_name("user-trash-symbolic", Gtk.IconSize.BUTTON); rm.set_tooltip_text("Remove (from this palette, or from saved colors)")
        rm.connect("clicked", self.remove_current); head.pack_start(rm, False, False, 0)

        pk = Gtk.Box(spacing=16); ed.pack_start(pk, False, False, 0)
        self.sv = SVPicker(self.on_sv, self.push); pk.pack_start(self.sv, True, True, 0)
        self.prev = Preview(); pk.pack_start(self.prev, False, False, 0)
        self.hue = Bar("hue", self.on_hue, self.push); ed.pack_start(self.hue, False, False, 0)
        self.abar = Bar("alpha", self.on_alpha, self.push); ed.pack_start(self.abar, False, False, 0)

        ed.pack_start(self.section("Values"), False, False, 0)
        grid = Gtk.Grid(row_spacing=8, column_spacing=10); ed.pack_start(grid, False, False, 0)
        self.hexe = Gtk.Entry(hexpand=True, placeholder_text="#RRGGBB or #RRGGBBAA"); self.hexe.get_style_context().add_class("mono"); self.hexe.connect("activate", self.on_hex_entry)
        grid.attach(Gtk.Label(label="HEX", xalign=0), 0, 0, 1, 1); grid.attach(self.hexe, 1, 0, 1, 1); grid.attach(self.cbtn("HEX"), 2, 0, 1, 1)
        self.vals = {}
        for i, k in enumerate(FORMATS[1:], 1):
            l = Gtk.Label(xalign=0, selectable=True); l.get_style_context().add_class("mono"); self.vals[k] = l
            grid.attach(Gtk.Label(label=k, xalign=0), 0, i, 1, 1); grid.attach(l, 1, i, 1, 1); grid.attach(self.cbtn(k), 2, i, 1, 1)

        ed.pack_start(self.section("Harmonies"), False, False, 0)
        hb2 = Gtk.Box(spacing=8, homogeneous=True); ed.pack_start(hb2, False, False, 0)
        self.hars = [Swatch(-1, 34, 9, self.set_hex) for _ in range(5)]
        for s in self.hars: hb2.pack_start(s, True, True, 0)
        ed.pack_start(self.section("Shades and tints"), False, False, 0)
        sb = Gtk.Box(spacing=6, homogeneous=True); ed.pack_start(sb, False, False, 0)
        self.shades = [Swatch(-1, 30, 8, self.set_hex) for _ in range(9)]
        for s in self.shades: sb.pack_start(s, True, True, 0)

        ed.pack_start(self.section("Contrast"), False, False, 0)
        cb = Gtk.Box(spacing=10, homogeneous=True); ed.pack_start(cb, False, False, 0)
        self.ct = [Gtk.Label(xalign=0, margin=12) for _ in range(2)]
        for l in self.ct: cb.pack_start(l, True, True, 0)
        fx = Gtk.Button(label="Adjust to reach AA"); fx.connect("clicked", self.fix_aa); ed.pack_start(fx, False, False, 0)

        act = Gtk.Box(spacing=10); ed.pack_start(act, False, False, 0)
        b = Gtk.Button(label="Add to palette"); b.connect("clicked", self.add_to_palette); act.pack_start(b, True, True, 0)
        b = Gtk.Button(label="Generate palette"); b.connect("clicked", self.generate); act.pack_start(b, True, True, 0)
        b = Gtk.Button(label="Pick from screen  (Ctrl+Shift+C)"); b.get_style_context().add_class("primary")
        b.connect("clicked", lambda *_: self.pick()); act.pack_start(b, True, True, 0)

        self.refresh_nav(); self.set_hex("#6B4EFF"); ed.show_all()

    # ----- small builders -----
    def section(self, t):
        l = Gtk.Label(label=t, xalign=0); l.get_style_context().add_class("sec"); return l
    def cbtn(self, fmt):
        b = Gtk.Button.new_from_icon_name("edit-copy-symbolic", Gtk.IconSize.BUTTON); b.set_tooltip_text("Copy " + fmt)
        def go(*_):
            copy(self.fmt()[fmt]); b.set_image(Gtk.Image.new_from_icon_name("emblem-ok-symbolic", Gtk.IconSize.BUTTON))
            GLib.timeout_add(900, lambda: b.set_image(Gtk.Image.new_from_icon_name("edit-copy-symbolic", Gtk.IconSize.BUTTON)) or False)
        b.connect("clicked", go); return b
    def fmt(self): return formats(self.rgb, self.alpha)
    def key(self): return to_hex(self.rgb, self.alpha)
    def entry_for(self, k): return next((c for c in self.data["colors"] if c["hex"] == k), None)
    def commit(self): save_json(DATA, self.data)
    def set_pick_copy(self, c): self.conf["pick_copy"] = c.get_active_text(); save_json(CONF, self.conf)

    # ----- color state + undo -----
    def set_hex(self, hx, push=True):
        p = parse_hex(hx)
        if not p: return
        self.rgb, self.alpha = p; h, s, v = colorsys.rgb_to_hsv(*[c / 255 for c in self.rgb])
        if s > 0 and v > 0: self.sv.h = h
        self.sv.s, self.sv.v = s, v; self.sync()
        if push: self.push()
    def push(self, *_):
        st = (self.key(), self.sv.h)
        if self.hist and self.hist[self.hi] == st: return
        del self.hist[self.hi + 1:]; self.hist.append(st); self.hist = self.hist[-100:]; self.hi = len(self.hist) - 1
    def undo(self, d):
        ni = self.hi + d
        if 0 <= ni < len(self.hist):
            self.hi = ni; hx, h = self.hist[ni]; self.set_hex(hx, push=False); self.sv.h = h; self.sync()
    def on_sv(self, s, v): self.rgb = hsv2rgb(self.sv.h, s, v); self.sync(drag=True)
    def on_hue(self, h): self.sv.h = h; self.rgb = hsv2rgb(h, self.sv.s, self.sv.v); self.sync(drag=True)
    def on_alpha(self, a): self.alpha = round(a, 2); self.sync(drag=True)
    def on_hex_entry(self, e): self.set_hex(e.get_text())
    def fix_aa(self, *_):
        ref = (255, 255, 255) if contrast(self.rgb, (255, 255, 255)) >= contrast(self.rgb, DARK) else DARK
        h, l, s = colorsys.rgb_to_hls(*[c / 255 for c in self.rgb]); step = -.01 if ref[0] == 255 else .01
        for _ in range(100):
            if contrast(self.rgb, ref) >= 4.5: break
            l = min(1, max(0, l + step)); self.rgb = hls2rgb(h, l, s)
        self.set_hex(self.key())

    def sync(self, drag=False):
        k, f = self.key(), self.fmt(); h = self.sv.h
        self.big.set_hex(k); self.sv.queue_draw(); self.hue.v = h; self.hue.queue_draw()
        self.abar.rgb, self.abar.v = self.rgb, self.alpha; self.abar.queue_draw(); self.prev.rgb, self.prev.a = self.rgb, self.alpha; self.prev.queue_draw()
        if not self.hexe.is_focus(): self.hexe.set_text(k)
        for n, l in self.vals.items(): l.set_text(f[n])
        s, v = self.sv.s, self.sv.v
        for sw, d in zip(self.hars, (180, 30, -30, 120, 150)): sw.set_hex(to_hex(hsv2rgb((h + d / 360) % 1, s, v)))
        _, hl, hs = colorsys.rgb_to_hls(*[c / 255 for c in self.rgb])
        for sw, l in zip(self.shades, (.92, .82, .72, .62, .52, .42, .32, .22, .12)): sw.set_hex(to_hex(hls2rgb(h, l, hs)))
        for lab, ref, nm in zip(self.ct, ((255, 255, 255), DARK), ("White text", "Dark text")):
            c = contrast(self.rgb, ref); lab.set_text("%s   %.2f:1   %s" % (nm, c, badge(c)))
            tint(lab, to_hex(self.rgb), "#ffffff" if ref[0] == 255 else "#15101f", 10)
        e = self.entry_for(k)
        if not self.name.is_focus(): self.name.set_text(e["name"] if e else k)
        self.sub.set_text(("Saved  •  " + when(e["ts"])) if e else "Not saved")
        self.favb.set_label("★" if e and e.get("fav") else "☆")
        if not drag:
            self.lock = True
            for row in self.lst.get_children():
                if row.hex == k: self.lst.select_row(row)
            self.lock = False

    # ----- saved colors -----
    def save_current(self, name=None):
        k = self.key(); e = self.entry_for(k)
        if e: e["ts"] = time.time()
        else: self.data["colors"].append({"hex": k, "name": name or k, "fav": False, "ts": time.time()})
        self.commit(); self.refresh_nav(); self.sync()
    def rename(self, *_):
        n, k = self.name.get_text().strip(), self.key(); e = self.entry_for(k)
        if not n or n == (e["name"] if e else k): return False
        if e: e["name"] = n; self.commit(); self.refresh_list()
        else: self.save_current(n)
        return False
    def toggle_fav(self, *_):
        self.save_current(); e = self.entry_for(self.key()); e["fav"] = not e.get("fav"); self.commit(); self.refresh_nav(); self.sync()
    def remove_current(self, *_):
        k = self.key()
        if self.filter.startswith("pal:"):
            p = self.data["palettes"].get(self.filter[4:], [])
            if k in p: p.remove(k)
        else: self.data["colors"] = [c for c in self.data["colors"] if c["hex"] != k]
        self.commit(); self.refresh_nav(); self.sync()

    # ----- palettes -----
    def add_to_palette(self, btn):
        m = Gtk.Menu()
        for n in self.data["palettes"]:
            it = Gtk.MenuItem(label=n); it.connect("activate", lambda _, n=n: self.put(n, [self.key()])); m.append(it)
        it = Gtk.MenuItem(label="New palette..."); it.connect("activate", lambda *_: self.new_palette([self.key()])); m.append(it)
        m.show_all(); m.popup_at_widget(btn, Gdk.Gravity.NORTH_WEST, Gdk.Gravity.SOUTH_WEST, None)
    def put(self, name, keys):
        p = self.data["palettes"].setdefault(name, [])
        for k in keys:
            if k not in p: p.append(k)
        self.commit(); self.refresh_nav()
    def new_palette(self, keys=()):
        d = Gtk.Dialog(title="New palette", transient_for=self, modal=True)
        d.add_button("Cancel", Gtk.ResponseType.CANCEL); d.add_button("Create", Gtk.ResponseType.OK)
        e = Gtk.Entry(placeholder_text="Palette name", activates_default=True); d.get_content_area().pack_start(e, True, True, 12)
        d.set_default_response(Gtk.ResponseType.OK); d.show_all()
        if d.run() == Gtk.ResponseType.OK and e.get_text().strip(): self.put(e.get_text().strip(), list(keys))
        d.destroy()
    def generate(self, *_):
        h, s, v = self.sv.h, self.sv.s, self.sv.v
        out = [to_hex(hsv2rgb((h + d / 360) % 1, s, v)) for d in (0, 30, -30, 180, 150)]
        out += [to_hex(hsv2rgb(h, s * .35, 1)), to_hex(hsv2rgb(h, min(1, s + .1), v * .25))]
        n = "Generated " + to_hex(self.rgb); self.put(n, out); self.filter = "pal:" + n; self.refresh_nav()
    def css_vars(self, n):
        slug = re.sub(r"[^a-z0-9]+", "-", n.lower()).strip("-") or "color"
        return ":root {\n" + "".join("  --%s-%d: %s;\n" % (slug, i + 1, k) for i, k in enumerate(self.data["palettes"][n])) + "}"
    def export(self, n):
        d = Gtk.FileChooserNative.new("Export palette", self, Gtk.FileChooserAction.SAVE, "Save", "Cancel")
        d.set_current_name(n + ".gpl"); d.set_do_overwrite_confirmation(True)
        if d.run() == Gtk.ResponseType.ACCEPT:
            lines = ["GIMP Palette", "Name: " + n, "Columns: 4", "#"] + ["%3d %3d %3d %s" % (*parse_hex(k)[0], k) for k in self.data["palettes"][n]]
            with open(d.get_filename(), "w") as f: f.write("\n".join(lines) + "\n")
    def del_pal(self, n):
        self.data["palettes"].pop(n, None)
        if self.filter == "pal:" + n: self.filter = "all"
        self.commit(); self.refresh_nav()
    def nav_click(self, lb, e):
        if e.button != 3: return False
        row = lb.get_row_at_y(int(e.y))
        if not row or not getattr(row, "key", "").startswith("pal:"): return False
        n = row.key[4:]; m = Gtk.Menu()
        for label, fn in (("Copy as CSS variables", lambda: copy(self.css_vars(n))), ("Export as GIMP palette...", lambda: self.export(n)), ("Delete palette", lambda: self.del_pal(n))):
            it = Gtk.MenuItem(label=label); it.connect("activate", lambda _, fn=fn: fn()); m.append(it)
        m.show_all(); m.popup_at_pointer(e); return True

    # ----- sidebar / list -----
    def nav_row(self, key, label, count, icon=None, hx=None):
        r = Gtk.ListBoxRow(); r.key = key; r.get_style_context().add_class("nav"); b = Gtk.Box(spacing=12)
        if icon: b.pack_start(Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.MENU), False, False, 0)
        else:
            sw = Swatch(20, 16, 4); sw.set_hex(hx); b.pack_start(sw, False, False, 0)
            r.drag_dest_set(Gtk.DestDefaults.ALL, TGT, Gdk.DragAction.COPY)
            r.connect("drag-data-received", lambda w, c, x, y, sel, i, t: GLib.idle_add(self.put, w.key[4:], [sel.get_text()]))
        b.pack_start(Gtk.Label(label=label, xalign=0), True, True, 0)
        c = Gtk.Label(label=str(count)); c.get_style_context().add_class("dim"); b.pack_end(c, False, False, 0)
        r.add(b); return r
    def refresh_nav(self):
        for r in self.nav.get_children(): self.nav.remove(r)
        cs = self.data["colors"]; self.lock = True
        for k, l, n, i in (("all", "All Colors", len(cs), "applications-graphics-symbolic"),
                           ("recent", "Recent", min(8, len(cs)), "document-open-recent-symbolic"),
                           ("fav", "Favorites", sum(1 for c in cs if c.get("fav")), "starred-symbolic")):
            self.nav.add(self.nav_row(k, l, n, i))
        hd = Gtk.ListBoxRow(selectable=False, activatable=False); b = Gtk.Box(margin=10)
        b.pack_start(self.section("Palettes"), True, True, 0)
        pb = Gtk.Button.new_from_icon_name("list-add-symbolic", Gtk.IconSize.BUTTON); pb.connect("clicked", lambda *_: self.new_palette()); b.pack_end(pb, False, False, 0)
        hd.add(b); self.nav.add(hd)
        for n, p in self.data["palettes"].items(): self.nav.add(self.nav_row("pal:" + n, n, len(p), None, p[0] if p else "#7A55F0"))
        self.nav.show_all()
        for r in self.nav.get_children():
            if getattr(r, "key", None) == self.filter: self.nav.select_row(r)
        self.lock = False; self.refresh_list()
    def on_nav(self, lb, row):
        if row is not None and not self.lock: self.filter = row.key; self.refresh_list()
    def refresh_list(self):
        for r in self.lst.get_children(): self.lst.remove(r)
        cs, q, f = self.data["colors"], self.search.get_text().lower(), self.filter
        if f == "recent": items = sorted(cs, key=lambda c: -c["ts"])[:8]
        elif f == "fav": items = [c for c in cs if c.get("fav")]
        elif f.startswith("pal:"): items = [self.entry_for(k) or {"hex": k, "name": k, "ts": 0} for k in self.data["palettes"].get(f[4:], [])]
        else: items = sorted(cs, key=lambda c: -c["ts"])
        items = [c for c in items if q in c["name"].lower() or q in c["hex"].lower()]
        if not items:
            r = Gtk.ListBoxRow(selectable=False, activatable=False); r.hex = None
            l = Gtk.Label(label="Nothing here yet.\nPick a color from the screen\nor press + to save one.", margin=24); l.get_style_context().add_class("dim"); r.add(l); self.lst.add(r)
        for c in items:
            r = Gtk.ListBoxRow(); r.hex = c["hex"]; r.get_style_context().add_class("item"); b = Gtk.Box(spacing=12)
            sw = Swatch(38, 38, 10); sw.set_hex(c["hex"]); b.pack_start(sw, False, False, 0)
            m = Gtk.Box(orientation=Gtk.Orientation.VERTICAL); m.pack_start(Gtk.Label(label=c["name"], xalign=0), False, False, 0)
            hl = Gtk.Label(label=c["hex"], xalign=0); hl.get_style_context().add_class("dim"); hl.get_style_context().add_class("mono"); m.pack_start(hl, False, False, 0)
            b.pack_start(m, True, True, 0)
            if c.get("ts"):
                t = Gtk.Label(label=when(c["ts"]), valign=Gtk.Align.START); t.get_style_context().add_class("dim"); b.pack_end(t, False, False, 0)
            r.add(b); r.drag_source_set(Gdk.ModifierType.BUTTON1_MASK, TGT, Gdk.DragAction.COPY)
            r.connect("drag-data-get", lambda w, ctx, sel, i, t: sel.set_text(w.hex, -1)); self.lst.add(r)
        self.lst.show_all(); self.lock = True
        for r in self.lst.get_children():
            if r.hex == self.key(): self.lst.select_row(r)
        self.lock = False
    def on_row(self, lb, row):
        if row is not None and not self.lock and row.hex: self.set_hex(row.hex)

    # ----- screen picking -----
    def pick(self, *_):
        vis = self.get_visible()
        if vis: self.hide(); GLib.timeout_add(250, self._start, vis)
        else: self._start(False)
    def _start(self, show_after): ScreenPicker(lambda hx: self._picked(hx, show_after)).start(); return False
    def _picked(self, hx, show_after):
        if show_after: self.present()
        if not hx: return
        self.set_hex(hx); self.save_current(); text = self.fmt()[self.conf.get("pick_copy", "HEX")]; copy(text)
        if not show_after: notify("Color copied", text); self.app.arm_idle()
    def on_key(self, w, e):
        ctrl, shift = e.state & Gdk.ModifierType.CONTROL_MASK, e.state & Gdk.ModifierType.SHIFT_MASK
        typing = isinstance(self.get_focus(), Gtk.Editable)
        if ctrl and shift and e.keyval in (Gdk.KEY_C, Gdk.KEY_c): self.pick(); return True
        if ctrl and not typing and e.keyval in (Gdk.KEY_z, Gdk.KEY_Z): self.undo(1 if shift else -1); return True
        if ctrl and not typing and e.keyval in (Gdk.KEY_y, Gdk.KEY_Y): self.undo(1); return True
        if ctrl and e.keyval in (Gdk.KEY_s, Gdk.KEY_S): self.save_current(); return True
        if ctrl and e.keyval in (Gdk.KEY_f, Gdk.KEY_F): self.search.grab_focus(); return True
        return False


class Application(Gtk.Application):
    """Single instance: `colorchooser --pick` from a hotkey talks to the running process."""
    def __init__(self):
        super().__init__(application_id="io.github.HamzaAkramv15.ColorChooser", flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.win, self.idle = None, 0
    def do_startup(self):
        Gtk.Application.do_startup(self); self.hold()
        p = Gtk.CssProvider(); p.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), p, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    def do_command_line(self, cl):
        ap = argparse.ArgumentParser(prog="colorchooser"); ap.add_argument("--hex"); ap.add_argument("--pick", action="store_true")
        try: a, _ = ap.parse_known_args(cl.get_arguments()[1:])
        except SystemExit: return 0
        if not self.win: self.win = Win(self)
        if a.hex: self.win.set_hex(a.hex)
        if a.pick: self.win.pick()
        else: self.win.show_all(); self.win.present()
        return 0
    def arm_idle(self):
        """After a hotkey pick with no window, stay alive 5 min so the clipboard survives, then quit."""
        if self.idle: GLib.source_remove(self.idle)
        self.idle = GLib.timeout_add_seconds(300, self._idle)
    def _idle(self):
        self.idle = 0
        if self.win and self.win.get_visible(): return False
        Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).store(); self.quit(); return False


if __name__ == "__main__":
    import sys
    sys.exit(Application().run(sys.argv))
