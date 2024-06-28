from typing import Any


# https://en.wikipedia.org/wiki/ANSI_escape_code#Colors
_BLUE = 94
_RED = 91
_GREEN = 92
_RESET = 0


def number(x: Any) -> str:
    return _raw(_BLUE) + str(x) + _raw(_RESET)


def danger(x: Any) -> str:
    return _raw(_RED) + str(x) + _raw(_RESET)


def code(x: Any) -> str:
    return _raw(_GREEN) + str(x) + _raw(_RESET)


def _raw(code: int) -> str:
    if not _ENABLED:
        return ""

    return f"\033[{code}m"


_ENABLED = True


def enable() -> None:
    global _ENABLED
    _ENABLED = True


def disable() -> None:
    global _ENABLED
    _ENABLED = False
