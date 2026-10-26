"""Media yang lagi diputar di Windows (YouTube di browser, Spotify, dll.).

Pakai Global System Media Transport Controls: sumber yang sama dengan kotak
media yang muncul waktu tombol volume ditekan.
"""

import asyncio
import threading

from winrt.windows.media.control import (
    GlobalSystemMediaTransportControlsSessionManager as SessionManager,
    GlobalSystemMediaTransportControlsSessionPlaybackStatus as Status,
)
from winrt.windows.storage.streams import Buffer, InputStreamOptions

POLL = 0.5


async def _read_thumbnail(ref):
    if ref is None:
        return None
    stream = await ref.open_read_async()
    buf = Buffer(stream.size)
    await stream.read_async(buf, stream.size, InputStreamOptions.READ_AHEAD)
    return bytes(buf)


class Media:
    """`info` selalu berisi snapshot terbaru (dict) atau None kalau gak ada yang diputar."""

    def __init__(self):
        self.info = None
        self.manager = None
        self.art_key = None
        self.art = None
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self.loop.run_until_complete, args=(self._watch(),),
                         daemon=True).start()

    def send(self, action):
        """action: 'playpause' | 'next' | 'prev'"""
        asyncio.run_coroutine_threadsafe(self._send(action), self.loop)

    async def _send(self, action):
        session = self.manager and self.manager.get_current_session()
        if session is None:
            return
        method = {"playpause": session.try_toggle_play_pause_async,
                  "next": session.try_skip_next_async,
                  "prev": session.try_skip_previous_async}[action]
        await method()
        self.info = await self._snapshot()

    async def _watch(self):
        while True:
            try:
                if self.manager is None:
                    self.manager = await SessionManager.request_async()
                self.info = await self._snapshot()
            except Exception:
                self.info = None
            await asyncio.sleep(POLL)

    async def _snapshot(self):
        session = self.manager.get_current_session()
        if session is None:
            return None
        status = session.get_playback_info().playback_status
        if status not in (Status.PLAYING, Status.PAUSED):
            return None
        props = await session.try_get_media_properties_async()
        if not props.title:
            return None

        key = (session.source_app_user_model_id, props.title, props.artist)
        if key != self.art_key:
            try:
                self.art = await _read_thumbnail(props.thumbnail)
            except Exception:
                self.art = None
            self.art_key = key

        timeline = session.get_timeline_properties()
        duration = (timeline.end_time - timeline.start_time).total_seconds()
        return {
            "title": props.title,
            "artist": props.artist or props.album_artist or "",
            "playing": status == Status.PLAYING,
            "art": self.art,
            "art_key": key,
            "position": timeline.position.total_seconds(),
            "duration": duration if duration > 0 else 0.0,
            "stamp": timeline.last_updated_time.timestamp(),
        }
