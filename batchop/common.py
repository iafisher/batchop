import decimal
import re
from pathlib import Path
from typing import Optional, Union

from . import colors


class BatchOpError(Exception):
    pass


class BatchOpSyntaxError(BatchOpError):
    pass


class BatchOpImpossibleError(BatchOpError):
    pass


PathLike = Union[str, Path]
NumberLike = Union[int, float, decimal.Decimal, str]
PatternLike = Union[str, re.Pattern]


def unit_to_multiple(unit: str) -> Optional[int]:
    unit = unit.lower()
    if unit in ("b", "byte", "bytes"):
        return 1
    elif unit in ("kb", "kilobyte", "kilobytes"):
        return 1000
    elif unit in ("mb", "megabyte", "megabytes"):
        return 1_000_000
    elif unit in ("gb", "gigabyte", "gigabytes"):
        return 1_000_000_000
    elif unit in ("tb", "terabyte", "terabytes"):
        return 1_000_000_000_000
    else:
        return None


def plural(n: int, s: str, ss: str = "", color: bool = False) -> str:
    if not ss:
        ss = s + "s"

    n_s = f"{n:,}"
    if color:
        n_s = colors.number(n_s)

    return f"{n_s} {s}" if n == 1 else f"{n_s} {ss}"
