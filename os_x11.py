"""Bagian khusus Linux (sesi X11/Xorg): jendela aktif, keyboard, idle, klik-tembus, dll.

Pakai python-xlib dan properti EWMH standar (_NET_ACTIVE_WINDOW, _NET_WM_STATE, ...),
jadi jalan di GNOME/KDE/XFCE selama sesinya Xorg. Di Wayland ini tidak bisa jalan.
"""

import fcntl
import os
import sys
import tempfile
import time

from Xlib import X, XK, Xatom, display, error
from Xlib.ext import shape
from Xlib.protocol import event

# WM_CLASS (lowercase) -> label
TERMINALS = {
    "gnome-terminal-server": "Terminal", "gnome-terminal": "Terminal",
    "org.gnome.terminal": "Terminal", "org.gnome.console": "Console", "kgx": "Console",
    "org.gnome.ptyxis": "Ptyxis", "xfce4-terminal": "Terminal", "konsole": "Konsole",
    "tilix": "Tilix", "terminator": "Terminator", "guake": "Guake", "tilda": "Tilda",
    "kitty": "kitty", "alacritty": "Alacritty", "org.wezfurlong.wezterm": "WezTerm",
    "com.mitchellh.ghostty": "Ghostty", "ghostty": "Ghostty", "dev.warp.warp": "Warp",
    "tabby": "Tabby", "hyper": "Hyper", "terminology": "Terminology",
    "com.raggesilver.blackbox": "Black Box", "xterm": "XTerm", "uxterm": "XTerm",
    "urxvt": "urxvt", "st-256color": "st", "foot": "foot", "rio": "Rio",
}

# menu "Mengetik": kunci -> (label, WM_CLASS, nyala bawaan)
TYPING_APPS = {
    "terminal": ("Terminal", set(TERMINALS), True),
    "word": ("LibreOffice Writer", {"libreoffice-writer"}, False),
    "excel": ("LibreOffice Calc", {"libreoffice-calc"}, False),
    "notepad": ("Text Editor", {"gedit", "org.gnome.gedit", "gnome-text-editor",
                                "org.gnome.texteditor", "mousepad", "xed", "pluma", "kate",
                                "kwrite"}, False),
    "browser": ("Browser", {"firefox", "firefox_firefox", "google-chrome", "chromium",
                            "chromium-browser", "brave-browser", "microsoft-edge", "opera",
                            "vivaldi-stable", "zen"}, False),
    "vscode": ("VS Code", {"code", "code - insiders", "code-oss", "vscodium"}, True),
}
KNOWN_APPS = set().union(*(ids for _, ids, _ in TYPING_APPS.values()))

AUTOSTART_FILE =os.path.join(os.path.expanduser("~"), ".config", "autostart", "notch.desktop")

MODIFIER_NAMES = ("Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R",
                  "Super_L", "Super_R", "Meta_L", "Meta_R", "Caps_Lock", "ISO_Level3_Shift")


class Platform:
    FONT = "Ubuntu"
    TERMINALS = TERMINALS
    MENU_FLUSH = False  # notch di bawah top bar GNOME, biarkan melayang
    TYPING_APPS = TYPING_APPS

    def __init__(self):
        self.d = display.Display()
        self.d.set_error_handler(lambda *_: None)  # jendela bisa keburu ditutup: abaikan BadWindow
        self.root = self.d.screen().root
        self.atoms = {}
        self.own_pid = os.getpid()
        self.win = None
        self.click_through = None
        self.has_idle = self.d.has_extension("MIT-SCREEN-SAVER")
        self.has_shape = self.d.has_extension("SHAPE")
        self.last_state = None
        self.last_active = time.monotonic()

        def keycode(name):
            return self.d.keysym_to_keycode(XK.string_to_keysym(name))

        self.KEY_ENTER = keycode("Return")
        self.KEY_BACKSPACE = keycode("BackSpace")
        self.KEY_C = keycode("c")
        self.CTRL_KEYS = {keycode("Control_L"), keycode("Control_R")}
        self.MODIFIER_KEYS = {keycode(n) for n in MODIFIER_NAMES} - {0}
        # di luar terminal cuma tombol yang menghasilkan teks yang dihitung ngetik
        text = [chr(c) for c in range(ord("a"), ord("z") + 1)] + [str(d) for d in range(10)]
        text += [f"KP_{d}" for d in range(10)]
        text += ["space", "Return", "KP_Enter", "BackSpace", "minus", "equal", "bracketleft",
                 "bracketright", "backslash", "semicolon", "apostrophe", "grave", "comma",
                 "period", "slash"]
        self.TEXT_KEYS = {keycode(n) for n in text} - {0}

    def atom(self, name):
        if name not in self.atoms:
            self.atoms[name] = self.d.intern_atom(name)
        return self.atoms[name]

    def window(self, wid):
        return self.d.create_resource_object("window", wid)

    # ---- jendela aktif
    def active_window(self):
        try:
            prop = self.root.get_full_property(self.atom("_NET_ACTIVE_WINDOW"), Xatom.WINDOW)
        except error.XError:
            return 0
        return prop.value[0] if prop and len(prop.value) else 0

    def window_app(self, wid):
        """WM_CLASS (lowercase); None kalau jendelanya milik notch sendiri."""
        if not wid:
            return ""
        try:
            w = self.window(wid)
            pid = w.get_full_property(self.atom("_NET_WM_PID"), Xatom.CARDINAL)
            if pid and pid.value[0] == self.own_pid:
                return None
            names = [n.lower() for n in (w.get_wm_class() or ()) if n]
        except error.XError:
            return ""
        # Firefox: WM_CLASS ("Navigator", "firefox"), jadi cari nama yang dikenal dulu
        return next((n for n in names if n in KNOWN_APPS), names[0] if names else "")

    def window_title(self, wid):
        if not wid:
            return ""
        try:
            w = self.window(wid)
            title = w.get_full_text_property(self.atom("_NET_WM_NAME"), self.atom("UTF8_STRING"))
            return title or w.get_wm_name() or ""
        except error.XError:
            return ""

    def window_rect(self, wid):
        try:
            w = self.window(wid)
            geo = w.get_geometry()
            pos = w.translate_coords(self.root, 0, 0)  # (0,0) root dilihat dari jendela
        except error.XError:
            return None
        x, y = -pos.x, -pos.y
        return x, y, x + geo.width, y + geo.height

    def is_fullscreen(self, wid):
        if not wid:
            return False
        try:
            state = self.window(wid).get_full_property(self.atom("_NET_WM_STATE"), Xatom.ATOM)
        except error.XError:
            return False
        return bool(state) and self.atom("_NET_WM_STATE_FULLSCREEN") in state.value

    # ---- input
    def keys_down(self):
        try:
            keymap = self.d.query_keymap()
        except error.XError:
            return set()
        return {i * 8 + bit for i, byte in enumerate(keymap) for bit in range(8) if byte >> bit & 1}

    def mouse_down(self):
        """True kalau ada tombol mouse (kiri/kanan/tengah) yang sedang ditekan."""
        try:
            mask = self.root.query_pointer().mask
        except error.XError:
            return False
        return bool(mask & (X.Button1Mask | X.Button2Mask | X.Button3Mask))

    def idle_seconds(self):
        if self.has_idle:
            try:
                return self.root.screensaver_query_info().idle / 1000.0
            except error.XError:
                pass
        # cadangan tanpa ekstensi MIT-SCREEN-SAVER: hitung sendiri dari keyboard & pointer
        try:
            ptr = self.root.query_pointer()
            state = (tuple(self.d.query_keymap()), ptr.root_x, ptr.root_y, ptr.mask)
        except error.XError:
            return 0.0
        now = time.monotonic()
        if state != self.last_state:
            self.last_state, self.last_active = state, now
        return now - self.last_active

    # ---- jendela notch
    def notch_top(self, screen):
        return screen.availableGeometry().y()  # tepat di bawah top bar GNOME

    def setup_window(self, widget):
        self.win = self.window(int(widget.winId()))
        # selalu di atas, ada di semua workspace, gak muncul di dock / alt-tab
        for a, b in (("_NET_WM_STATE_ABOVE", "_NET_WM_STATE_STICKY"),
                     ("_NET_WM_STATE_SKIP_TASKBAR", "_NET_WM_STATE_SKIP_PAGER")):
            ev = event.ClientMessage(window=self.win, client_type=self.atom("_NET_WM_STATE"),
                                     data=(32, [1, self.atom(a), self.atom(b), 1, 0]))
            self.root.send_event(ev, event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask)
        self.d.flush()
        self.set_click_through(True, None)

    def set_click_through(self, on, region):
        """Atur area yang bisa diklik lewat input shape: kosong = tembus semua."""
        key = (on, region)
        if key == self.click_through or not self.win or not self.has_shape:
            return
        self.click_through = key
        rects = [] if on else [region]
        self.win.shape_rectangles(shape.SO.Set, shape.SK.Input, X.Unsorted, 0, 0, rects)
        self.d.flush()

    def keep_on_top(self):
        pass  # sudah diurus window manager lewat _NET_WM_STATE_ABOVE

    def take_focus(self):
        pass  # ketikan ditangkap lewat grabKeyboard() Qt (XGrabKeyboard), tanpa ganti fokus

    def release_focus(self):
        pass

    # ---- lain-lain
    def single_instance(self):
        """File lock kalau ini satu-satunya notch yang jalan, None kalau sudah ada."""
        path = os.path.join(os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir(),
                            "notch-iseng.lock")
        f = open(path, "w")
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            f.close()
            return None
        return f

    def autostart_enabled(self):
        return os.path.exists(AUTOSTART_FILE)

    def set_autostart(self, on, script):
        if not on:
            if os.path.exists(AUTOSTART_FILE):
                os.remove(AUTOSTART_FILE)
            return
        os.makedirs(os.path.dirname(AUTOSTART_FILE), exist_ok=True)
        with open(AUTOSTART_FILE, "w", encoding="utf-8") as f:
            f.write("[Desktop Entry]\nType=Application\nName=Notch\n"
                    f"Exec=\"{sys.executable}\" \"{script}\"\n"
                    "X-GNOME-Autostart-enabled=true\nX-GNOME-Autostart-Delay=3\n")
