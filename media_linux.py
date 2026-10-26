"""Media yang lagi diputar di Linux lewat MPRIS (D-Bus).

Chrome/Chromium, Firefox, Spotify, VLC, dll. semuanya mendaftarkan diri sebagai
org.mpris.MediaPlayer2.<nama> di session bus.
"""

import queue
import threading
import time
import urllib.parse
import urllib.request

from jeepney import DBusAddress, Properties, new_method_call
from jeepney.bus_messages import message_bus
from jeepney.io.blocking import open_dbus_connection
from jeepney.wrappers import unwrap_msg

PREFIX = "org.mpris.MediaPlayer2."
PATH = "/org/mpris/MediaPlayer2"
PLAYER_IFACE = "org.mpris.MediaPlayer2.Player"
POLL = 0.5
METHODS = {"playpause": "PlayPause", "next": "Next", "prev": "Previous"}


def _value(d, key, default):
    """Properti D-Bus datang sebagai (signature, value)."""
    return d[key][1] if key in d else default


def _load_art(url):
    if url.startswith("file://"):
        with open(urllib.parse.unquote(urllib.parse.urlparse(url).path), "rb") as f:
            return f.read()
    if url.startswith(("http://", "https://")):
        req = urllib.request.Request(url, headers={"User-Agent": "notch-iseng"})
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.read()
    return None


class Media:
    """`info` selalu berisi snapshot terbaru (dict) atau None kalau gak ada yang diputar."""

    def __init__(self):
        self.info = None
        self.current = None  # bus name player yang lagi ditampilkan
        self.art_url = None
        self.art = None
        self.actions = queue.Queue()
        threading.Thread(target=self._run, daemon=True).start()

    def send(self, action):
        """action: 'playpause' | 'next' | 'prev'"""
        self.actions.put(action)

    def _run(self):
        while True:
            try:
                conn = open_dbus_connection(bus="SESSION")
                while True:
                    self.info = self._snapshot(conn)
                    try:
                        action = self.actions.get(timeout=POLL)
                    except queue.Empty:
                        continue
                    if self.current:
                        addr = DBusAddress(PATH, bus_name=self.current, interface=PLAYER_IFACE)
                        conn.send_and_get_reply(new_method_call(addr, METHODS[action]), timeout=2)
            except Exception:
                self.info = None
                time.sleep(3)  # bus putus / belum siap: coba lagi nanti

    def _snapshot(self, conn):
        names = unwrap_msg(conn.send_and_get_reply(message_bus.ListNames(), timeout=2))[0]
        players = {}
        for name in names:
            if not name.startswith(PREFIX) or name.endswith(".playerctld"):
                continue
            addr = DBusAddress(PATH, bus_name=name, interface=PLAYER_IFACE)
            try:
                players[name] = unwrap_msg(
                    conn.send_and_get_reply(Properties(addr).get_all(), timeout=1))[0]
            except Exception:
                continue

        def status(name):
            return _value(players[name], "PlaybackStatus", "Stopped")

        # utamakan yang lagi main; kalau semua jeda, tetap di player terakhir
        playing = [n for n in players if status(n) == "Playing"]
        paused = [n for n in players if status(n) == "Paused"]
        candidates = playing or paused
        if not candidates:
            self.current = None
            return None
        self.current = self.current if self.current in candidates else candidates[0]

        props = players[self.current]
        meta = _value(props, "Metadata", {})
        title = _value(meta, "xesam:title", "")
        if not title:
            return None
        art_url = _value(meta, "mpris:artUrl", "")
        if art_url != self.art_url:
            try:
                self.art = _load_art(art_url) if art_url else None
            except Exception:
                self.art = None
            self.art_url = art_url

        artist = _value(meta, "xesam:artist", [])
        return {
            "title": title,
            "artist": ", ".join(artist) if isinstance(artist, list) else str(artist),
            "playing": status(self.current) == "Playing",
            "art": self.art,
            "art_key": (self.current, title, art_url),
            "position": _value(props, "Position", 0) / 1e6,
            "duration": _value(meta, "mpris:length", 0) / 1e6,
            "stamp": time.time(),
        }
