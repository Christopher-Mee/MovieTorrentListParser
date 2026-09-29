# Christopher Mee
# 2026-09-28
# Windows console debug helper class.
# Prints debug info to the console and allows clearing it when done. Also
# scrolls the console window back up, when user typed command is out of view.
# Known issues: Not designed for debugging in the middle of script output. Only
# at the start.
import ctypes
from ctypes import wintypes


class COORD(ctypes.Structure):
    _fields_ = [
        ("X", wintypes.SHORT),
        ("Y", wintypes.SHORT),
    ]


class SMALL_RECT(ctypes.Structure):
    _fields_ = [
        ("Left", wintypes.SHORT),
        ("Top", wintypes.SHORT),
        ("Right", wintypes.SHORT),
        ("Bottom", wintypes.SHORT),
    ]


class CONSOLE_SCREEN_BUFFER_INFO(ctypes.Structure):
    _fields_ = [
        ("dwSize", COORD),
        ("dwCursorPosition", COORD),
        ("wAttributes", wintypes.WORD),
        ("srWindow", SMALL_RECT),
        ("dwMaximumWindowSize", COORD),
    ]


class ConsoleDebug:
    STD_OUTPUT_HANDLE = -11

    def __init__(self):
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        # Declare the Win32 signatures. Without argtypes, ctypes passes the
        # Python str " " to FillConsoleOutputCharacterW as a char* pointer,
        # so the console gets filled with the low 16 bits of that pointer
        # (a garbage character) instead of a space.
        self.kernel32.GetStdHandle.argtypes = [wintypes.DWORD]
        self.kernel32.GetStdHandle.restype = wintypes.HANDLE

        self.kernel32.GetConsoleScreenBufferInfo.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(CONSOLE_SCREEN_BUFFER_INFO),
        ]
        self.kernel32.GetConsoleScreenBufferInfo.restype = wintypes.BOOL

        self.kernel32.FillConsoleOutputCharacterW.argtypes = [
            wintypes.HANDLE,
            wintypes.WCHAR,
            wintypes.DWORD,
            COORD,
            ctypes.POINTER(wintypes.DWORD),
        ]
        self.kernel32.FillConsoleOutputCharacterW.restype = wintypes.BOOL

        self.kernel32.FillConsoleOutputAttribute.argtypes = [
            wintypes.HANDLE,
            wintypes.WORD,
            wintypes.DWORD,
            COORD,
            ctypes.POINTER(wintypes.DWORD),
        ]
        self.kernel32.FillConsoleOutputAttribute.restype = wintypes.BOOL

        self.kernel32.SetConsoleCursorPosition.argtypes = [
            wintypes.HANDLE,
            COORD,
        ]
        self.kernel32.SetConsoleCursorPosition.restype = wintypes.BOOL

        self.kernel32.SetConsoleWindowInfo.argtypes = [
            wintypes.HANDLE,
            wintypes.BOOL,
            ctypes.POINTER(SMALL_RECT),
        ]
        self.kernel32.SetConsoleWindowInfo.restype = wintypes.BOOL

        self.handle = self.kernel32.GetStdHandle(self.STD_OUTPUT_HANDLE)

        # Anchor for clear(): cursor row when the helper was created, i.e.
        # the first row after the command that launched the program. The
        # typed command itself sits on the row just above it.
        self._anchor_y = self._get_info().dwCursorPosition.Y
        self._start = None
        self._end = None

    def _get_info(self):
        info = CONSOLE_SCREEN_BUFFER_INFO()

        if not self.kernel32.GetConsoleScreenBufferInfo(
            self.handle, ctypes.byref(info)
        ):
            raise ctypes.WinError(ctypes.get_last_error())

        return info

    def print(self, *args, **kwargs):
        if self._start is None:
            self._start = self._get_info().dwCursorPosition

        print(*args, **kwargs)

        self._end = self._get_info().dwCursorPosition

    def ask(self, prompt=""):
        if self._start is None:
            self._start = self._get_info().dwCursorPosition

        answer = input(prompt)

        # input() echoes the typed text and leaves the cursor on the line
        # below after Enter. Track it so clear() wipes the prompt line and
        # that extra line instead of leaving a hanging row behind.
        self._end = self._get_info().dwCursorPosition

        return answer.strip().lower() == "y"

    def clear(self):
        if self._start is None or self._end is None:
            return

        info = self._get_info()
        width = info.dwSize.X
        written = wintypes.DWORD()

        for y in range(self._start.Y, self._end.Y + 1):
            position = COORD(0, y)

            self.kernel32.FillConsoleOutputCharacterW(
                self.handle,
                " ",
                width,
                position,
                ctypes.byref(written),
            )

            self.kernel32.FillConsoleOutputAttribute(
                self.handle,
                info.wAttributes,
                width,
                position,
                ctypes.byref(written),
            )

        self.kernel32.SetConsoleCursorPosition(
            self.handle,
            self._start,
        )

        # If the debug output scrolled the typed command out of view, scroll
        # the viewport back up just enough to show the command line again.
        # If everything fit on screen the command is still visible, so the
        # viewport is left alone.
        info = self._get_info()
        command_y = max(0, self._anchor_y - 1)
        if command_y < info.srWindow.Top:
            wnd = info.srWindow
            new_top = command_y
            new_wnd = SMALL_RECT(
                wnd.Left, new_top, wnd.Right, new_top + (wnd.Bottom - wnd.Top)
            )
            self.kernel32.SetConsoleWindowInfo(
                self.handle,
                True,
                ctypes.byref(new_wnd),
            )

        self._start = None
        self._end = None
