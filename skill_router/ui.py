"""Терминальная эстетика: баннер + ANSI-цвета. Кроссплатформенно, уважает NO_COLOR."""
import os
import sys

_BANNER = r"""
 ╔═╗╦╔═╦╦  ╦    ╦═╗╔═╗╦ ╦╔╦╗╔═╗╦═╗
 ╚═╗╠╩╗║║  ║    ╠╦╝║ ║║ ║ ║ ║╣ ╠╦╝
 ╚═╝╩ ╩╩╩═╝╩═╝  ╩╚═╚═╝╚═╝ ╩ ╚═╝╩╚═"""


def _color_on():
    if os.environ.get("NO_COLOR"):
        return False
    if not sys.stdout.isatty():
        return False
    return True


_ON = None


def _enable_windows_ansi():
    if os.name == "nt":
        try:
            import ctypes
            k = ctypes.windll.kernel32
            k.SetConsoleMode(k.GetStdHandle(-11), 7)  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
        except Exception:
            pass


def c(code, s):
    global _ON
    if _ON is None:
        _ON = _color_on()
        if _ON:
            _enable_windows_ansi()
    return f"\033[{code}m{s}\033[0m" if _ON else s


def bold(s):   return c("1", s)
def dim(s):    return c("2", s)
def cyan(s):   return c("36", s)
def green(s):  return c("32", s)
def blue(s):   return c("34;1", s)
def yellow(s): return c("33", s)
def red(s):    return c("31", s)
def gray(s):   return c("90", s)


def banner(subtitle="semantic router for Claude Code skills"):
    lines = [c("36;1", l) for l in _BANNER.strip("\n").splitlines()]
    out = "\n" + "\n".join(lines) + "\n"
    out += "  " + dim("$ ") + cyan("skill-router .") + dim("   ·   " + subtitle) + "\n"
    return out


def rule(width=54):
    return dim("─" * width)
