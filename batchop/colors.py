from typing import Any


_BLUE = 94
_RED = 91
_RESET = 0


def number(x: Any) -> str:
    return _raw(_BLUE) + str(x) + _raw(_RESET)


def danger(x: Any) -> str:
    return _raw(_RED) + str(x) + _raw(_RESET)


def _raw(code: int) -> str:
    return f"\033[{code}m"
