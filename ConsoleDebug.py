# Christopher Mee
# 2026-09-28
# Windows console debug helper class.
# Prints debug info to the console and allows clearing it when done. Also
# scrolls the console window back up, when user typed command is out of view.
# Known issues: Not designed for debugging in the middle of script output. Only
# at the beginning.
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
        # Viewport top when the helper was created. Restoring this (rather
        # than forcing the command line to the top) keeps the window exactly
        # where the user had it.
        self._initial_top = self._get_info().srWindow.Top
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

    def restoreViewport(self):
        # put the viewport back exactly where it was when the helper was
        # created, so the command line stays where the user left it instead
        # of jumping to the top
        info = self._get_info()

        if info.srWindow.Top == self._initial_top:
            return

        wnd = info.srWindow
        new_wnd = SMALL_RECT(
            wnd.Left,
            self._initial_top,
            wnd.Right,
            self._initial_top + (wnd.Bottom - wnd.Top),
        )
        self.kernel32.SetConsoleWindowInfo(
            self.handle,
            True,
            ctypes.byref(new_wnd),
        )

    def autoScrollThenAsk(self, prompt=""):
        # If the last printed output scrolled out of view, print the prompt
        # normally, then restore the original viewport so every row can be
        # screened top-to-bottom. input() writes nothing more, so the viewport
        # stays put until the first echo'd keystroke pulls it back down --
        # exactly when the user starts answering. Falls back to ask() when
        # nothing scrolled.
        if (
            self._start is not None
            and self._end is not None
            and self._start.Y < self._get_info().srWindow.Top
        ):
            self.print(prompt, end="")
            self.restoreViewport()

            result = input()
            self._end = self._get_info().dwCursorPosition

            return result.strip().lower() == "y"

        return self.ask(prompt)

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

        # Put the viewport back where it was before the debug output scrolled
        # it away, so the command line stays where the user left it.
        self.restoreViewport()

        self._start = None
        self._end = None
