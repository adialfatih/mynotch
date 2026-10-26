"""
Notch — Dynamic Island iseng buat Windows & Ubuntu (Xorg).

Perilaku:
  * Selalu nongol di tengah atas layar (always-on-top, gak muncul di taskbar).
  * Lagi di terminal -> notch melebar, matanya ngeliatin kamu ngetik.
      - Enter     : riak + "terkirim"
      - Backspace : geleng-geleng
      - Ctrl+C    : kaget
      - Judul terminal berubah-ubah cepat (spinner Claude Code / Codex) -> "lagi mikir"
    Privasi: cuma mendeteksi *ada* tombol ditekan; isi ketikan tidak dibaca/disimpan.
  * Di luar terminal -> matanya ngikutin mouse; kalau mouse diem, lirik-lirik sendiri.
  * Gak ada input 60 detik -> tidur.
  * Hover -> jam. Klik -> seneng. Klik 5x cepet -> pusing. Klik kanan -> menu.
  * Klik 2x -> waktu sholat berikutnya (lokasi diatur manual lewat klik kanan,
    data Kemenag dari api.myquran.com, disimpan per bulan di notch_settings.json).
  * Ada musik/video main (YouTube, Spotify, ...) -> indikator kecil + mata manggut-manggut;
    ganti lagu -> notifikasi judul & artis; hover -> panel musik dengan ⏮ ⏯ ⏭.

Bagian yang khusus OS ada di os_windows.py / os_x11.py dan media_windows.py / media_linux.py.

Jalankan:  Windows -> jalankan.bat   |   Ubuntu -> ./install_ubuntu.sh lalu ./jalankan.sh
"""

import json
import math
import os
import random
import signal
import sys
import threading
import time
import urllib.parse
import urllib.request
from collections import deque
from datetime import date, datetime, timedelta

if sys.platform == "win32":
    from os_windows import Platform
else:
    os.environ.setdefault("QT_QPA_PLATFORM", "xcb")  # X11 API cuma bisa dipakai di jendela X11
    from os_x11 import Platform

try:  # fitur musik opsional: kalau paketnya belum dipasang, notch tetap jalan tanpa musik
    if sys.platform == "win32":
        from media_windows import Media
    else:
        from media_linux import Media
except ImportError as exc:
    print(f"Fitur musik nonaktif: {exc}", file=sys.stderr)
    Media = None

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (QColor, QCursor, QFont, QFontMetrics, QPainter,
                           QPainterPath, QPen, QPixmap, QPolygonF)
from PySide6.QtWidgets import QApplication, QMenu, QWidget

# ------------------------------------------------------------------ pengaturan
SLEEP_AFTER = 60.0      # detik tanpa input sebelum tidur
TYPING_HOLD = 1.4       # berapa lama dianggap "masih ngetik" setelah tombol terakhir
WIN_W, WIN_H = 560, 160 # kanvas transparan (lebih besar dari pil, buat riak & partikel)
TOP_GAP = 8
HIT_REGION = (WIN_W // 2 - 215, 0, 430, TOP_GAP + 70)  # area klik saat hover (X11)
MEDIA_TOAST = 3.5       # detik notifikasi lagu baru tampil

CLAUDE_GLYPHS = "✳✻✽✶✢"

COL_MOUSE = (236, 238, 245)
COL_TERM = (95, 225, 150)
COL_CLAUDE = (217, 119, 87)
COL_CODEX = (110, 190, 255)
COL_SLEEP = (120, 120, 135)
COL_SHOLAT = (110, 215, 190)
COL_MEDIA = (250, 130, 180)
CONFETTI = [(255, 120, 160), (255, 210, 90), (120, 220, 255), (160, 255, 150)]

HARI = ["Sen", "Sel", "Rab", "Kam", "Jum", "Sab", "Min"]
BULAN = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]

SCRIPT = os.path.abspath(__file__)
SETTINGS_FILE = os.path.join(os.path.dirname(SCRIPT), "notch_settings.json")

SHOLAT_API = "https://api.myquran.com/v3/sholat"
SHOLAT = [("subuh", "Subuh"), ("dzuhur", "Dzuhur"), ("ashar", "Ashar"),
          ("maghrib", "Maghrib"), ("isya", "Isya")]
PRAYER_SHOW = 7.0  # detik panel sholat tampil setelah klik 2x


def load_settings():
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_settings(settings):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)


# ------------------------------------------------------------------ jadwal sholat
def http_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "notch-iseng"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)


def cari_kota(keyword):
    """[{'id': ..., 'lokasi': 'KOTA PEKALONGAN'}, ...]"""
    data = http_json(f"{SHOLAT_API}/kabkota/cari/{urllib.parse.quote(keyword)}")
    return (data.get("data") or []) if data.get("status") else []


def jadwal_bulan(kota_id, year, month):
    """{'2026-10-26': {'subuh': '03:59', ...}, ...}"""
    data = http_json(f"{SHOLAT_API}/jadwal/{kota_id}/{year:04d}-{month:02d}")
    return data["data"]["jadwal"]


def next_prayer(jadwal, now):
    """(nama, 'HH:MM', datetime) sholat berikutnya; None kalau jadwalnya belum ada."""
    for offset in (0, 1):
        d = now.date() + timedelta(days=offset)
        hari = jadwal.get(d.isoformat())
        if not hari:
            return None
        for key, nama in SHOLAT:
            h, m = map(int, hari[key].split(":"))
            at = datetime(d.year, d.month, d.day, h, m)
            if at > now:
                return nama, hari[key], at
    return None


def countdown(delta):
    mins = max(1, math.ceil(delta.total_seconds() / 60))
    if mins < 60:
        return f"{mins} menit lagi"
    return f"{mins // 60} jam {mins % 60} menit lagi" if mins % 60 else f"{mins // 60} jam lagi"


# ------------------------------------------------------------------ animasi
def clamp(v, lo=0.0, hi=1.0):
    return lo if v < lo else hi if v > hi else v


def lerp(a, b, t):
    return a + (b - a) * t


def smoothstep(t):
    return t * t * (3 - 2 * t)


class Spring:
    """Pegas teredam: x mengejar target dengan sedikit mantul ala iOS."""

    def __init__(self, x, stiffness, damping):
        self.x = self.target = float(x)
        self.v = 0.0
        self.k = stiffness
        self.c = 2 * math.sqrt(stiffness) * damping

    def step(self, dt):
        for _ in range(2):
            h = dt / 2
            self.v += (self.k * (self.target - self.x) - self.c * self.v) * h
            self.x += self.v * h


# ------------------------------------------------------------------ notch
class Notch(QWidget):
    def __init__(self, plat):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                         | Qt.Tool | Qt.WindowDoesNotAcceptFocus)
        self.plat = plat
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.resize(WIN_W, WIN_H)
        self.place()

        self.pw = Spring(160, 220, 0.62)
        self.ph = Spring(34, 220, 0.62)
        self.py = Spring(0, 260, 0.35)
        self.expand = Spring(0, 160, 0.9)
        self.look_x = Spring(0, 140, 0.75)
        self.look_y = Spring(0.3, 140, 0.75)
        self.open = Spring(1, 260, 0.45)
        self.happy = Spring(0, 200, 0.9)
        self.lid = Spring(0, 200, 0.9)
        self.sleepf = Spring(0, 90, 1.0)
        self.musicf = Spring(0, 160, 0.9)
        self.alpha = Spring(0, 120, 1.0)
        self.springs = [self.pw, self.ph, self.py, self.expand, self.look_x, self.look_y,
                        self.open, self.happy, self.lid, self.sleepf, self.musicf, self.alpha]
        self.color = list(COL_MOUSE)

        now = time.perf_counter()
        self.t0 = self.last = now
        self.settings = load_settings()
        self.hide_on_fullscreen = self.settings.get("hide_on_fullscreen", True)
        self.jadwal = self.settings.get("jadwal", {})
        self.fetching = False
        self.prayer_until = 0.0
        self.fullscreen = False
        self.next_slow_check = 0.0
        self.mode = "mouse"

        self.fg_win = 0
        self.fg_app = ""
        self.fg_title = ""
        self.fg_rect = None
        self.in_terminal = False
        self.agent_name = None
        self.title_changes = deque()

        self.kb_prev = None
        self.last_key = -99.0
        self.line_len = 0
        self.bars = [0.0] * 6

        self.prev_cursor = QCursor.pos()
        self.last_mouse_move = now
        self.next_saccade = 0.0
        self.saccade = (0.0, 0.3)
        self.sleeping = False

        self.blink = 1.0
        self.blink_start = -99.0
        self.next_blink = now + 2.0
        self.happy_until = 0.0
        self.startle_until = 0.0
        self.startle_cooldown = 0.0
        self.shake_until = 0.0
        self.dizzy_until = 0.0
        self.flash_text = ""
        self.flash_until = 0.0
        self.clicks = []
        self.ripples = []
        self.particles = []

        self.media = None
        if Media:
            try:
                self.media = Media()
            except Exception as exc:
                print(f"Fitur musik nonaktif: {exc}", file=sys.stderr)
        self.track = None
        self.track_key = None
        self.toast_until = 0.0
        self.bobbing = False
        self.art_pixmap = None
        self.art_key = None
        self.btn_pressed = None
        self.btn_pressed_at = -99.0

        self.font_label = QFont(plat.FONT, 9, QFont.DemiBold)
        self.font_clock = QFont(plat.FONT, 13, QFont.Bold)
        self.font_small = QFont(plat.FONT, 8)
        self.font_z = QFont(plat.FONT, 8, QFont.Bold)
        self.ensure_jadwal()

        self.alpha.target = 1.0
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.PreciseTimer)
        self.timer.timeout.connect(self.tick)
        self.timer.start(16)

    def place(self):
        scr = QApplication.primaryScreen()
        geo = scr.geometry()
        self.move(geo.x() + (geo.width() - WIN_W) // 2, self.plat.notch_top(scr))

    # -------------------------------------------------------------- input
    def update_foreground(self, now):
        win = self.plat.active_window()
        if win != self.fg_win:
            app = self.plat.window_app(win)
            if app is None:  # menu / notch sendiri: pertahankan konteks sebelumnya
                return
            self.fg_win = win
            self.fg_app = app
            self.fg_title = self.plat.window_title(win) if win else ""
            self.in_terminal = app in self.plat.TERMINALS
            self.title_changes.clear()
            self.kb_prev = None
            self.line_len = 0
        elif self.in_terminal:
            title = self.plat.window_title(win)
            if title != self.fg_title:
                self.fg_title = title
                self.title_changes.append(now)

        self.agent_name = None
        if self.in_terminal:
            low = self.fg_title.lower()
            if "claude" in low or self.fg_title[:1] in CLAUDE_GLYPHS:
                self.agent_name = "Claude Code"
            elif "codex" in low:
                self.agent_name = "Codex"

    def poll_keys(self, now):
        down = self.plat.keys_down()
        if self.kb_prev is None:  # baru masuk terminal: jangan hitung tombol yang lagi ditahan
            self.kb_prev = down
            return
        pressed = down - self.kb_prev
        self.kb_prev = down
        ctrl = bool(down & self.plat.CTRL_KEYS)
        for key in pressed:
            if key not in self.plat.MODIFIER_KEYS:
                self.on_key(key, ctrl, now)

    def on_key(self, key, ctrl, now):
        self.last_key = now
        self.ph.v += 45
        if ctrl and key == self.plat.KEY_C:
            self.startle(now, 0.6)
            self.shake_until = now + 0.35
            self.flash("eh?! dibatalin", now, 1.2)
            self.line_len = 0
        elif key == self.plat.KEY_ENTER:
            self.line_len = 0
            self.ripples.append(0.0)
            self.happy_until = now + 0.5
            self.flash("terkirim ✓" if self.agent_name else "enter ↵", now, 1.0)
        elif key == self.plat.KEY_BACKSPACE:
            self.line_len = max(0, self.line_len - 1)
            self.shake_until = now + 0.22
            self.bump_bars(0.5)
        else:
            self.line_len += 1
            self.bump_bars(1.0)

    def bump_bars(self, level):
        self.bars = [max(b, random.uniform(0.35, 1.0) * level) for b in self.bars]

    def startle(self, now, dur):
        self.startle_until = now + dur
        self.startle_cooldown = now + 2.0

    def flash(self, text, now, dur):
        self.flash_text = text
        self.flash_until = now + dur

    def register_click(self, now):
        """Catat klik; True kalau barusan jadi pusing (5 klik dalam 2.5 detik)."""
        self.clicks = [c for c in self.clicks if now - c < 2.5] + [now]
        if len(self.clicks) < 5:
            return False
        self.clicks.clear()
        self.prayer_until = 0.0
        self.dizzy_until = now + 2.6
        self.flash("pusing…", now, 2.6)
        return True

    def mousePressEvent(self, e):
        now = time.perf_counter()
        if e.button() == Qt.RightButton:
            self.show_menu(e.globalPosition().toPoint())
            return
        if e.button() != Qt.LeftButton:
            return
        action = self.media_button_at(e.position())
        if action:
            self.press_media(action, now)
            return
        if not self.register_click(now):
            self.happy_until = now + 1.1
        self.py.v += 160
        self.burst()

    def mouseDoubleClickEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        now = time.perf_counter()
        action = self.media_button_at(e.position())
        if action:  # klik cepat beruntun di tombol = tekan tombol lagi
            self.press_media(action, now)
            return
        if self.register_click(now):
            return
        self.py.v += 120
        self.show_prayer(now)

    # -------------------------------------------------------------- musik
    def media_buttons(self, rect):
        """[(aksi, titik tengah)] tombol ⏮ ⏯ ⏭ di sisi kanan panel musik."""
        mid = rect.center().y()
        return [(action, QPointF(rect.right() - 31 - (2 - i) * 30, mid))
                for i, action in enumerate(("prev", "playpause", "next"))]

    def media_button_at(self, pos):
        if self.mode != "media" or not self.track or not self.media:
            return None
        for action, c in self.media_buttons(self.pill_rect()):
            if math.hypot(pos.x() - c.x(), pos.y() - c.y()) <= 15:
                return action
        return None

    def press_media(self, action, now):
        self.media.send(action)
        self.btn_pressed, self.btn_pressed_at = action, now
        if action != "playpause":  # lirik ke arah tombol yang ditekan
            self.look_x.v += 9 if action == "next" else -9

    def update_track(self, now):
        info = self.media.info if self.media else None
        self.track = info
        if not info:
            return
        key = (info["title"], info["artist"])
        if key != self.track_key:
            self.track_key = key
            if info["playing"]:
                self.toast_until = now + MEDIA_TOAST
        if info["art_key"] != self.art_key:
            self.art_key = info["art_key"]
            self.art_pixmap = None
            pix = QPixmap()
            if info["art"] and pix.loadFromData(info["art"]):
                side = min(pix.width(), pix.height())  # potong tengah jadi persegi (thumbnail YouTube 16:9)
                pix = pix.copy((pix.width() - side) // 2, (pix.height() - side) // 2, side, side)
                self.art_pixmap = pix.scaled(96, 96, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)

    def track_progress(self):
        info = self.track
        if not info or info["duration"] <= 0:
            return None
        pos = info["position"]
        elapsed = time.time() - info["stamp"]
        if info["playing"] and 0 <= elapsed < 6 * 3600:
            pos += elapsed
        return clamp(pos / info["duration"])

    def burst(self):
        rect = self.pill_rect()
        for _ in range(16):
            ang = random.uniform(0.15 * math.pi, 0.85 * math.pi)
            speed = random.uniform(80, 220)
            x = rect.center().x() + random.uniform(-rect.width() / 3, rect.width() / 3)
            self.particles.append([x, rect.bottom() - 4, math.cos(ang) * speed,
                                   math.sin(ang) * speed, 1.0, random.choice(CONFETTI)])

    def show_menu(self, pos):
        menu = QMenu()
        menu.setStyleSheet(
            "QMenu{background:#111;color:#eee;border:1px solid #333;border-radius:8px;padding:4px}"
            "QMenu::item{padding:6px 18px;border-radius:5px}"
            "QMenu::item:selected{background:#2a2a2e}"
            "QMenu::separator{height:1px;background:#333;margin:4px 8px}")
        a_fs = menu.addAction("Sembunyi kalau ada app fullscreen")
        a_fs.setCheckable(True)
        a_fs.setChecked(self.hide_on_fullscreen)
        a_auto = menu.addAction("Jalan otomatis saat komputer nyala")
        a_auto.setCheckable(True)
        a_auto.setChecked(self.plat.autostart_enabled())
        lokasi = self.settings.get("sholat")
        a_loc = menu.addAction(f"Lokasi sholat: {lokasi['lokasi']}…" if lokasi
                               else "Atur lokasi sholat…")
        menu.addSeparator()
        a_quit = menu.addAction("Keluar")
        chosen = menu.exec(pos)
        if chosen is a_fs:
            self.hide_on_fullscreen = a_fs.isChecked()
            self.settings["hide_on_fullscreen"] = self.hide_on_fullscreen
            save_settings(self.settings)
        elif chosen is a_loc:
            self.ask_location()
        elif chosen is a_auto:
            self.plat.set_autostart(a_auto.isChecked(), SCRIPT)
        elif chosen is a_quit:
            QApplication.quit()

    # -------------------------------------------------------------- sholat
    def show_prayer(self, now):
        self.prayer_until = now + PRAYER_SHOW
        self.ensure_jadwal()

    def ensure_jadwal(self):
        """Ambil jadwal bulan ini (dan bulan depan kalau besok ganti bulan) di background."""
        lokasi = self.settings.get("sholat")
        if not lokasi or self.fetching:
            return
        today = date.today()
        days = [today, today + timedelta(days=1)]
        months = sorted({(d.year, d.month) for d in days if d.isoformat() not in self.jadwal})
        if not months:
            return
        self.fetching = True
        threading.Thread(target=self._fetch_jadwal, args=(lokasi["id"], months), daemon=True).start()

    def _fetch_jadwal(self, kota_id, months):
        try:
            got = {}
            for y, m in months:
                got.update(jadwal_bulan(kota_id, y, m))
            if self.settings.get("sholat", {}).get("id") != kota_id:
                return  # lokasi keburu diganti
            kemarin = (date.today() - timedelta(days=1)).isoformat()
            self.jadwal = {k: v for k, v in {**self.jadwal, **got}.items() if k >= kemarin}
            self.settings["jadwal"] = self.jadwal
            save_settings(self.settings)
        except Exception:
            pass  # panel akan bilang gagal; klik 2x lagi untuk coba ulang
        finally:
            self.fetching = False

    def ask_location(self):
        from PySide6.QtWidgets import QInputDialog, QMessageBox
        title = "Lokasi sholat"
        keyword, ok = QInputDialog.getText(None, title, "Nama kota/kabupaten (contoh: pekalongan):")
        keyword = keyword.strip()
        if not ok or not keyword:
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            hasil = cari_kota(keyword)
        except Exception:
            hasil = None
        finally:
            QApplication.restoreOverrideCursor()
        if hasil is None:
            QMessageBox.warning(None, title, "Gagal menghubungi server jadwal sholat. Cek internet.")
            return
        if not hasil:
            QMessageBox.information(None, title, f"\"{keyword}\" tidak ketemu. Coba nama lain.")
            return
        names = [h["lokasi"].title() for h in hasil]
        if len(hasil) == 1:
            idx = 0
        else:
            name, ok = QInputDialog.getItem(None, title, "Pilih yang benar:", names, 0, False)
            if not ok:
                return
            idx = names.index(name)
        self.settings["sholat"] = {"id": hasil[idx]["id"], "lokasi": names[idx]}
        self.jadwal = {}
        self.settings["jadwal"] = {}
        save_settings(self.settings)
        self.show_prayer(time.perf_counter())

    def prayer_lines(self):
        lokasi = self.settings.get("sholat")
        if not lokasi:
            return "Lokasi belum diatur", "klik kanan → Atur lokasi sholat"
        nxt = next_prayer(self.jadwal, datetime.now())
        if nxt:
            nama, jam, at = nxt
            return f"{nama}  {jam}", f"{countdown(at - datetime.now())} · {lokasi['lokasi']}"
        if self.fetching:
            return "Ambil jadwal…", lokasi["lokasi"]
        return "Gagal ambil jadwal", "cek internet, lalu klik 2x lagi"

    # -------------------------------------------------------------- logika
    def pill_rect(self):
        pw, ph = self.pw.x, self.ph.x
        return QRectF(WIN_W / 2 - pw / 2, TOP_GAP + self.py.x, pw, ph)

    def eye_anchor(self, rect):
        cx = lerp(rect.center().x(), rect.left() + 46, clamp(self.expand.x))
        return cx - self.sleepf.x * 14 - self.musicf.x * 16, rect.center().y()

    def look_at(self, gx, gy, rect):
        ex, ey = self.eye_anchor(rect)
        dx, dy = gx - (self.x() + ex), gy - (self.y() + ey)
        return dx / (abs(dx) + 220), clamp(dy / (abs(dy) + 140), -0.8, 1.0)

    def context_color(self):
        if not self.in_terminal:
            return COL_MOUSE
        return {"Claude Code": COL_CLAUDE, "Codex": COL_CODEX}.get(self.agent_name, COL_TERM)

    def tick(self):
        now = time.perf_counter()
        dt = min(now - self.last, 1 / 30)
        self.last = now
        t = now - self.t0

        cur = QCursor.pos()
        mdist = math.hypot(cur.x() - self.prev_cursor.x(), cur.y() - self.prev_cursor.y())
        self.prev_cursor = cur
        if mdist > 0:
            self.last_mouse_move = now

        self.update_foreground(now)
        if self.in_terminal:
            self.poll_keys(now)
        else:
            self.kb_prev = None
        self.update_track(now)
        playing = bool(self.track and self.track["playing"])

        was_sleeping = self.sleeping
        self.sleeping = self.plat.idle_seconds() > SLEEP_AFTER
        if was_sleeping and not self.sleeping:
            self.startle(now, 0.45)

        if now >= self.next_slow_check:
            self.next_slow_check = now + 0.5
            self.fullscreen = self.hide_on_fullscreen and self.plat.is_fullscreen(self.fg_win)
            self.fg_rect = self.plat.window_rect(self.fg_win) if self.fg_win else None
            self.place()
            self.plat.keep_on_top()

        rect = self.pill_rect()
        grect = rect.translated(self.x(), self.y())
        hovering = self.alpha.x > 0.5 and grect.adjusted(-6, -6, 6, 6).contains(QPointF(cur))
        self.plat.set_click_through(not hovering, HIT_REGION)

        # mouse ngebut lewat dekat notch -> kaget
        if not self.in_terminal and mdist / max(dt, 1e-3) > 4000 and now > self.startle_cooldown:
            ex, ey = self.eye_anchor(rect)
            if math.hypot(cur.x() - self.x() - ex, cur.y() - self.y() - ey) < 260:
                self.startle(now, 0.5)

        typing = self.in_terminal and now - self.last_key < TYPING_HOLD
        while self.title_changes and now - self.title_changes[0] > 2.5:
            self.title_changes.popleft()
        thinking = self.in_terminal and not typing and len(self.title_changes) >= 3

        if self.fullscreen:
            mode = "hidden"
        elif self.sleeping:
            mode = "sleep"
        elif now < self.prayer_until:
            mode = "prayer"
        elif hovering:
            mode = "media" if self.track else "hover"
        elif typing or thinking:
            mode = "thinking" if thinking else "typing"
        elif now < self.toast_until and self.track:
            mode = "media"
        elif self.in_terminal:
            mode = "terminal"
        else:
            mode = "mouse"
        self.mode = mode
        self.bobbing = playing and mode not in ("sleep", "typing", "hidden")

        # ---- target bentuk & ekspresi
        sizes = {"mouse": (190 if playing else 160, 34), "hidden": (160, 34), "sleep": (150, 32),
                 "hover": (270, 44), "typing": (310, 40), "terminal": (310, 40),
                 "thinking": (310, 40), "prayer": (320, 52), "media": (400, 58)}
        self.pw.target, self.ph.target = sizes[mode]
        self.alpha.target = 0.0 if mode == "hidden" else 1.0
        self.expand.target = 1.0 if mode in ("hover", "typing", "terminal", "thinking",
                                             "prayer", "media") else 0.0
        self.sleepf.target = 1.0 if mode == "sleep" else 0.0
        self.musicf.target = 1.0 if playing and mode == "mouse" else 0.0
        self.lid.target = 0.25 if mode == "typing" else 0.0
        self.happy.target = 1.0 if now < self.happy_until or mode in ("hover", "prayer",
                                                                      "media") else 0.0
        if mode == "sleep":
            self.open.target = 0.1
        else:
            self.open.target = 1.35 if now < self.startle_until else 1.0

        # ---- arah pandang
        if mode == "sleep":
            lx, ly = 0.0, 0.35
        elif mode == "typing":
            lx, ly = -0.55 + min(self.line_len, 48) / 48 * 1.1, 0.55
        elif mode == "thinking":
            lx, ly = 0.45 + 0.3 * math.sin(t * 0.9), -0.75
        elif mode == "terminal" and now - self.last_mouse_move > 1.5 and self.fg_rect:
            left, top, right, bottom = self.fg_rect
            dpr = self.devicePixelRatioF()
            lx, ly = self.look_at((left + (right - left) * 0.3) / dpr,
                                  (bottom - (bottom - top) * 0.12) / dpr, rect)
        elif mode == "mouse" and now - self.last_mouse_move > 3.5:
            if now >= self.next_saccade:
                self.next_saccade = now + random.uniform(1.0, 3.0)
                self.saccade = (random.uniform(-0.85, 0.85), random.uniform(-0.4, 0.8))
            lx, ly = self.saccade
        else:
            lx, ly = self.look_at(cur.x(), cur.y(), rect)
        self.look_x.target, self.look_y.target = lx, ly

        # ---- kedip
        if now >= self.next_blink and mode != "sleep" and now > self.dizzy_until:
            self.blink_start = now
            self.next_blink = now + (0.28 if random.random() < 0.18 else random.uniform(2.2, 6.0))
        bt = (now - self.blink_start) / 0.16
        self.blink = 1 - 0.95 * math.sin(math.pi * bt) if 0 <= bt < 1 else 1.0

        # ---- integrasi
        for s in self.springs:
            s.step(dt)
        target_col = ({"sleep": COL_SLEEP, "prayer": COL_SHOLAT, "media": COL_MEDIA}.get(mode)
                      or self.context_color())
        k = 1 - math.exp(-dt * 6)
        self.color = [lerp(c, tc, k) for c, tc in zip(self.color, target_col)]
        decay = math.exp(-dt * 5)
        self.bars = [b * decay for b in self.bars]
        self.ripples = [r + dt / 0.7 for r in self.ripples if r + dt / 0.7 < 1]
        for pt in self.particles:
            pt[3] += 380 * dt
            pt[0] += pt[2] * dt
            pt[1] += pt[3] * dt
            pt[4] -= dt / 1.1
        self.particles = [pt for pt in self.particles if pt[4] > 0]

        self.update()

    # -------------------------------------------------------------- gambar
    def paintEvent(self, _):
        a = clamp(self.alpha.x)
        if a < 0.01:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setOpacity(a)
        rect = self.pill_rect()
        radius = min(rect.height() / 2, 22)
        col = QColor(*[int(c) for c in self.color])

        p.setBrush(Qt.NoBrush)
        for rt in self.ripples:
            g = rt * 28
            c = QColor(col)
            c.setAlphaF(clamp((1 - rt) * 0.6))
            p.setPen(QPen(c, 2.0 * (1 - rt) + 0.6))
            p.drawRoundedRect(rect.adjusted(-g, -g, g, g), radius + g, radius + g)

        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        p.setPen(QPen(QColor(255, 255, 255, 26), 1))
        p.setBrush(QColor(0, 0, 0))
        p.drawPath(path)

        p.save()
        p.setClipPath(path)
        self.paint_eyes(p, rect, col)
        self.paint_content(p, rect, col, a)
        p.restore()

        p.setPen(Qt.NoPen)
        for x, y, _, _, life, pc in self.particles:
            c = QColor(*pc)
            c.setAlphaF(clamp(life))
            p.setBrush(c)
            p.drawEllipse(QPointF(x, y), 2.4, 2.4)
        p.end()

    def paint_eyes(self, p, rect, col):
        now = time.perf_counter()
        t = now - self.t0
        s = min(rect.height(), 44) / 36  # di panel tinggi (sholat/musik) mata gak ikut membesar
        cx, cy = self.eye_anchor(rect)
        lx, ly = self.look_x.x, self.look_y.x
        shake = math.sin(t * 60) * 2.4 * s if now < self.shake_until else 0.0
        openness = max(0.07, self.open.x * self.blink)
        bg = QColor(0, 0, 0)

        for side in (-1, 1):
            persp = 1 + 0.13 * lx * side  # mata di arah lirikan sedikit lebih besar
            ew = 13 * s * persp
            eh = 17 * s * persp * openness
            ex = cx + side * 14 * s + lx * 7 * s + shake
            ey = cy + ly * 5 * s
            if self.bobbing:  # manggut-manggut ikut musik
                ey += math.sin(t * 11) * 1.4 * s

            if now < self.dizzy_until:
                p.save()
                p.translate(ex, ey)
                p.rotate(t * 400 * side)
                pen = QPen(col, 2.4 * s)
                pen.setCapStyle(Qt.RoundCap)
                p.setPen(pen)
                d = 5 * s
                p.drawLine(QPointF(-d, -d), QPointF(d, d))
                p.drawLine(QPointF(-d, d), QPointF(d, -d))
                p.restore()
                continue

            r = min(ew, eh) / 2
            p.setPen(Qt.NoPen)
            for grow, al in ((5 * s, 0.10), (2.5 * s, 0.18)):
                g = QColor(col)
                g.setAlphaF(al)
                p.setBrush(g)
                p.drawRoundedRect(QRectF(ex - ew / 2 - grow, ey - eh / 2 - grow,
                                         ew + 2 * grow, eh + 2 * grow), r + grow, r + grow)
            p.setBrush(col)
            p.drawRoundedRect(QRectF(ex - ew / 2, ey - eh / 2, ew, eh), r, r)

            top = ey - eh / 2
            lid = self.lid.x
            if lid > 0.01:  # kelopak miring = muka fokus
                x0, x1 = ex - ew / 2 - 7 * s, ex + ew / 2 + 7 * s
                outer, inner = top + eh * lid * 0.45, top + eh * lid
                yl, yr = (outer, inner) if side < 0 else (inner, outer)
                p.setBrush(bg)
                p.drawPolygon(QPolygonF([QPointF(x0, top - 8 * s), QPointF(x1, top - 8 * s),
                                         QPointF(x1, yr), QPointF(x0, yl)]))
            hp = self.happy.x
            if hp > 0.01:  # potong bagian bawah -> mata senyum ∩
                p.setBrush(bg)
                p.drawEllipse(QPointF(ex, ey + eh * 0.5 + eh * (1 - hp) * 1.3 + 1), ew, eh * 0.62)

    def paint_content(self, p, rect, col, a):
        now = time.perf_counter()
        t = now - self.t0
        mid = rect.center().y()

        c = smoothstep(clamp((self.expand.x - 0.35) / 0.65))
        if c > 0.01:
            p.setOpacity(a * c)
            x0, x1 = rect.left() + 92, rect.right() - 16
            area = QRectF(x0, rect.top(), max(0.0, x1 - x0), rect.height())

            if self.mode == "media" and self.track:
                self.paint_media(p, rect)
            elif self.mode == "prayer":
                line1, line2 = self.prayer_lines()
                p.setFont(self.font_clock)
                p.setPen(QColor(245, 245, 250))
                p.drawText(QRectF(x0, rect.top() + 7, area.width(), 22),
                           Qt.AlignVCenter | Qt.AlignLeft, line1)
                p.setFont(self.font_small)
                p.setPen(QColor(150, 150, 160))
                p.drawText(QRectF(x0, rect.top() + 29, area.width(), 16),
                           Qt.AlignVCenter | Qt.AlignLeft,
                           QFontMetrics(self.font_small).elidedText(line2, Qt.ElideRight,
                                                                   int(area.width())))
            elif self.mode == "hover":
                lt = time.localtime()
                p.setFont(self.font_clock)
                p.setPen(QColor(245, 245, 250))
                p.drawText(area, Qt.AlignVCenter | Qt.AlignLeft, time.strftime("%H:%M", lt))
                p.setFont(self.font_label)
                p.setPen(QColor(150, 150, 160))
                p.drawText(area, Qt.AlignVCenter | Qt.AlignRight,
                           f"{HARI[lt.tm_wday]}, {lt.tm_mday} {BULAN[lt.tm_mon - 1]}")
            else:
                flash = now < self.flash_until
                name = self.agent_name or self.plat.TERMINALS.get(self.fg_app, "Terminal")
                if flash:
                    label = self.flash_text
                elif self.mode == "thinking":
                    label = f"{self.agent_name.split()[0]} lagi mikir" if self.agent_name \
                        else "lagi mikir"
                elif self.mode == "typing":
                    label = ""
                else:
                    label = f"{name}  ♪" if self.track and self.track["playing"] else name

                right_w = 0
                p.setPen(Qt.NoPen)
                p.setBrush(col)
                if self.mode == "thinking" and not flash:
                    right_w = 30
                    for i in range(3):
                        bounce = max(0.0, math.sin(t * 5 - i * 0.7))
                        p.drawEllipse(QPointF(x1 - 24 + i * 9 + 3, mid - bounce * 4), 2.6, 2.6)
                elif not flash:
                    bw, gap = 3, 3
                    right_w = len(self.bars) * (bw + gap) - gap
                    maxh = rect.height() - 16
                    for i, b in enumerate(self.bars):
                        h = 3 + b * maxh
                        p.drawRoundedRect(QRectF(x1 - right_w + i * (bw + gap), mid - h / 2, bw, h),
                                          1.5, 1.5)

                text_w = max(0.0, area.width() - right_w - 8)
                p.setFont(self.font_label)
                p.setPen(col if flash else QColor(215, 215, 222))
                text = QFontMetrics(self.font_label).elidedText(label, Qt.ElideRight, int(text_w))
                p.drawText(QRectF(x0, rect.top(), text_w, rect.height()),
                           Qt.AlignVCenter | Qt.AlignLeft, text)
            p.setOpacity(a)

        mf = self.musicf.x
        if mf > 0.02:  # indikator kecil "lagi ada musik" di notch mode ringkas
            mc = QColor(*COL_MEDIA)
            mc.setAlphaF(clamp(mf))
            p.setPen(Qt.NoPen)
            p.setBrush(mc)
            for i in range(4):
                h = 3 + (0.5 + 0.5 * math.sin(t * (7 + i * 1.7) + i * 1.3)) * 9
                p.drawRoundedRect(QRectF(rect.right() - 36 + i * 5, mid - h / 2, 2.6, h), 1.3, 1.3)

        sf = self.sleepf.x
        if sf > 0.02:
            for k in range(3):
                ph = (t * 0.45 + k / 3) % 1
                zc = QColor(col)
                zc.setAlphaF(clamp(sf * math.sin(math.pi * ph) * 0.9))
                f = QFont(self.font_z)
                f.setPointSizeF(6 + ph * 4)
                p.setFont(f)
                p.setPen(zc)
                p.drawText(QPointF(rect.right() - 40 + ph * 16,
                                   rect.bottom() - 6 - ph * (rect.height() - 12)), "z")


    def paint_media(self, p, rect):
        info = self.track
        now = time.perf_counter()
        mid = rect.center().y()

        cover = QRectF(rect.left() + 86, mid - 20, 40, 40)
        clip = QPainterPath()
        clip.addRoundedRect(cover, 8, 8)
        if self.art_pixmap:
            p.save()
            p.setClipPath(clip, Qt.IntersectClip)
            p.setRenderHint(QPainter.SmoothPixmapTransform)
            p.drawPixmap(cover, self.art_pixmap, QRectF(self.art_pixmap.rect()))
            p.restore()
        else:
            p.fillPath(clip, QColor(40, 40, 46))
            p.setPen(QColor(*COL_MEDIA))
            p.setFont(self.font_clock)
            p.drawText(cover, Qt.AlignCenter, "♪")

        buttons = self.media_buttons(rect)
        x0 = cover.right() + 10
        text_w = max(0.0, buttons[0][1].x() - 20 - x0)
        p.setFont(self.font_label)
        p.setPen(QColor(245, 245, 250))
        p.drawText(QRectF(x0, rect.top() + 10, text_w, 18), Qt.AlignVCenter | Qt.AlignLeft,
                   QFontMetrics(self.font_label).elidedText(info["title"], Qt.ElideRight, int(text_w)))
        p.setFont(self.font_small)
        p.setPen(QColor(150, 150, 160))
        p.drawText(QRectF(x0, rect.top() + 27, text_w, 16), Qt.AlignVCenter | Qt.AlignLeft,
                   QFontMetrics(self.font_small).elidedText(info["artist"], Qt.ElideRight, int(text_w)))

        progress = self.track_progress()
        if progress is not None:
            bar = QRectF(x0, rect.top() + 46, text_w, 2.5)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, 40))
            p.drawRoundedRect(bar, 1.2, 1.2)
            p.setBrush(QColor(*COL_MEDIA))
            p.drawRoundedRect(QRectF(bar.left(), bar.top(), bar.width() * progress, bar.height()),
                              1.2, 1.2)

        cur = self.mapFromGlobal(QCursor.pos())
        for action, c in buttons:
            pressed = action == self.btn_pressed and now - self.btn_pressed_at < 0.18
            if math.hypot(cur.x() - c.x(), cur.y() - c.y()) <= 15:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(255, 255, 255, 45 if pressed else 28))
                p.drawEllipse(c, 14, 14)
            icon = "pause" if action == "playpause" and info["playing"] else \
                "play" if action == "playpause" else action
            self.paint_icon(p, icon, c, 0.8 if pressed else 1.0)

    def paint_icon(self, p, icon, c, scale):
        p.save()
        p.translate(c)
        p.scale(scale, scale)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(245, 245, 250))
        if icon == "play":
            p.drawPolygon(QPolygonF([QPointF(-4, -6.5), QPointF(-4, 6.5), QPointF(7, 0)]))
        elif icon == "pause":
            p.drawRoundedRect(QRectF(-5.5, -6.5, 4, 13), 1.2, 1.2)
            p.drawRoundedRect(QRectF(1.5, -6.5, 4, 13), 1.2, 1.2)
        else:  # next; prev = next dicerminkan
            if icon == "prev":
                p.scale(-1, 1)
            p.drawPolygon(QPolygonF([QPointF(-6, -5.5), QPointF(-6, 5.5), QPointF(2.5, 0)]))
            p.drawRoundedRect(QRectF(3.5, -5.5, 2.4, 11), 1, 1)
        p.restore()


def main():
    if os.environ.get("XDG_SESSION_TYPE") == "wayland":
        print("Peringatan: sesi Wayland terdeteksi. Notch butuh sesi Xorg "
              "(layar login -> ikon gerigi -> 'Ubuntu on Xorg').", file=sys.stderr)
    plat = Platform()
    lock = plat.single_instance()  # disimpan supaya tetap terkunci selama app jalan
    if lock is None:
        return
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    w = Notch(plat)
    w.show()
    plat.setup_window(w)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
