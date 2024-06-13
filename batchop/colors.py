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
    return f"\033[{code}m"
