"""Bagian khusus Windows: jendela aktif, keyboard, idle, klik-tembus, dll. lewat Win32 API."""

import ctypes
import ctypes.wintypes as wt
import os
import subprocess
import sys

# nama proses terminal -> label
TERMINALS = {
    "windowsterminal.exe": "Terminal", "openconsole.exe": "Terminal",
    "conhost.exe": "Console", "cmd.exe": "CMD",
    "powershell.exe": "PowerShell", "pwsh.exe": "PowerShell",
    "wezterm-gui.exe": "WezTerm", "alacritty.exe": "Alacritty",
    "mintty.exe": "Git Bash", "hyper.exe": "Hyper", "tabby.exe": "Tabby",
    "warp.exe": "Warp", "conemu.exe": "ConEmu", "conemu64.exe": "ConEmu",
    "kitty.exe": "kitty", "rio.exe": "Rio", "ghostty.exe": "Ghostty",
}

STARTUP_LNK = os.path.join(os.environ.get("APPDATA", ""),
                           r"Microsoft\Windows\Start Menu\Programs\Startup\Notch.lnk")

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wt.UINT), ("dwTime", wt.DWORD)]


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("rcMonitor", wt.RECT),
                ("rcWork", wt.RECT), ("dwFlags", wt.DWORD)]


user32.GetForegroundWindow.restype = wt.HWND
user32.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
user32.GetClassNameW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
user32.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.c_short
user32.GetLastInputInfo.argtypes = [ctypes.POINTER(LASTINPUTINFO)]
user32.MonitorFromWindow.argtypes = [wt.HWND, wt.DWORD]
user32.MonitorFromWindow.restype = wt.HMONITOR
user32.MonitorFromPoint.argtypes = [wt.POINT, wt.DWORD]
user32.MonitorFromPoint.restype = wt.HMONITOR
user32.GetMonitorInfoW.argtypes = [wt.HMONITOR, ctypes.POINTER(MONITORINFO)]
user32.GetWindowLongPtrW.argtypes = [wt.HWND, ctypes.c_int]
user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.SetWindowLongPtrW.argtypes = [wt.HWND, ctypes.c_int, ctypes.c_ssize_t]
user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.SetWindowPos.argtypes = [wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, wt.UINT]
kernel32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
kernel32.OpenProcess.restype = wt.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = [wt.HANDLE, wt.DWORD, wt.LPWSTR,
                                                ctypes.POINTER(wt.DWORD)]
kernel32.CloseHandle.argtypes = [wt.HANDLE]
kernel32.GetTickCount.restype = wt.DWORD
kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wt.BOOL, wt.LPCWSTR]
kernel32.CreateMutexW.restype = wt.HANDLE

GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x20
WS_EX_TOOLWINDOW = 0x80
WS_EX_LAYERED = 0x80000
WS_EX_NOACTIVATE = 0x08000000
HWND_TOPMOST = wt.HWND(-1)
SWP_FLAGS = 0x0001 | 0x0002 | 0x0010  # NOSIZE | NOMOVE | NOACTIVATE
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
ERROR_ALREADY_EXISTS = 183


def _window_pid(hwnd):
    pid = wt.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def _process_name(pid):
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(520)
        n = wt.DWORD(520)
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)):
            return os.path.basename(buf.value).lower()
        return ""
    finally:
        kernel32.CloseHandle(h)


def _class_name(hwnd):
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def _rect(hwnd):
    r = wt.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r


class Platform:
    FONT = "Segoe UI"
    TERMINALS = TERMINALS

    KEY_ENTER, KEY_BACKSPACE, KEY_C = 0x0D, 0x08, 0x43
    CTRL_KEYS = {0xA2, 0xA3}
    MODIFIER_KEYS = {0x14, 0x5B, 0x5C, 0x5D, 0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5}
    WATCHED_KEYS = [vk for vk in range(0x08, 0xFF) if vk not in (0x10, 0x11, 0x12)]

    def __init__(self):
        self.hwnd = 0
        self.click_through = None
        self.own_pid = os.getpid()

    # ---- jendela aktif
    def active_window(self):
        return user32.GetForegroundWindow() or 0

    def window_app(self, hwnd):
        """Nama proses (lowercase); None kalau jendelanya milik notch sendiri."""
        pid = _window_pid(hwnd) if hwnd else 0
        if pid == self.own_pid:
            return None
        return _process_name(pid) if pid else ""

    def window_title(self, hwnd):
        buf = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(hwnd, buf, 512)
        return buf.value

    def window_rect(self, hwnd):
        r = _rect(hwnd)
        return r.left, r.top, r.right, r.bottom

    def is_fullscreen(self, hwnd):
        """True kalau jendela aktif menutupi seluruh monitor utama (game, video F11)."""
        if not hwnd or _class_name(hwnd) in ("Progman", "WorkerW", "Shell_TrayWnd"):
            return False
        mon = user32.MonitorFromWindow(hwnd, 2)
        if mon != user32.MonitorFromPoint(wt.POINT(0, 0), 1):
            return False
        mi = MONITORINFO()
        mi.cbSize = ctypes.sizeof(MONITORINFO)
        user32.GetMonitorInfoW(mon, ctypes.byref(mi))
        r, m = _rect(hwnd), mi.rcMonitor
        return r.left <= m.left and r.top <= m.top and r.right >= m.right and r.bottom >= m.bottom

    # ---- input
    def keys_down(self):
        return {vk for vk in self.WATCHED_KEYS if user32.GetAsyncKeyState(vk) & 0x8000}

    def idle_seconds(self):
        lii = LASTINPUTINFO(ctypes.sizeof(LASTINPUTINFO), 0)
        if not user32.GetLastInputInfo(ctypes.byref(lii)):
            return 0.0
        return ((kernel32.GetTickCount() - lii.dwTime) & 0xFFFFFFFF) / 1000.0

    # ---- jendela notch
    def notch_top(self, screen):
        return screen.geometry().y()

    def setup_window(self, widget):
        self.hwnd = int(widget.winId())
        ex = user32.GetWindowLongPtrW(self.hwnd, GWL_EXSTYLE)
        user32.SetWindowLongPtrW(self.hwnd, GWL_EXSTYLE, ex | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW)
        self.set_click_through(True, None)

    def set_click_through(self, on, region):
        # region tidak perlu: piksel transparan di layered window memang sudah tembus klik
        if on == self.click_through or not self.hwnd:
            return
        self.click_through = on
        ex = user32.GetWindowLongPtrW(self.hwnd, GWL_EXSTYLE)
        if not ex & WS_EX_LAYERED:  # WS_EX_TRANSPARENT cuma berlaku di layered window
            return
        ex = (ex | WS_EX_TRANSPARENT) if on else (ex & ~WS_EX_TRANSPARENT)
        user32.SetWindowLongPtrW(self.hwnd, GWL_EXSTYLE, ex)

    def keep_on_top(self):
        if self.hwnd:
            user32.SetWindowPos(self.hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_FLAGS)

    # ---- lain-lain
    def single_instance(self):
        """Handle mutex kalau ini satu-satunya notch yang jalan, None kalau sudah ada."""
        mutex = kernel32.CreateMutexW(None, False, "Local\\NotchIseng")
        if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
            kernel32.CloseHandle(mutex)
            return None
        return mutex

    def autostart_enabled(self):
        return os.path.exists(STARTUP_LNK)

    def set_autostart(self, on, script):
        if not on:
            if os.path.exists(STARTUP_LNK):
                os.remove(STARTUP_LNK)
            return
        pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
        ps = ("$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:N_LNK);"
              "$s.TargetPath=$env:N_PYW;$s.Arguments='\"'+$env:N_SCRIPT+'\"';"
              "$s.WorkingDirectory=$env:N_DIR;$s.Save()")
        env = dict(os.environ, N_LNK=STARTUP_LNK, N_PYW=pyw, N_SCRIPT=script,
                   N_DIR=os.path.dirname(script))
        subprocess.run(["powershell", "-NoProfile", "-Command", ps], env=env,
                       creationflags=0x08000000, check=False)
