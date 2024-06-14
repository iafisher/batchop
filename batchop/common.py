import decimal
import re
import sys
from pathlib import Path
from typing import Any, NoReturn, Optional, Union

from . import colors


class BatchOpError(Exception):
    pass


class BatchOpSyntaxError(BatchOpError):
    pass


# not a subclass of BatchOpError as it should not be caught
class BatchOpImpossibleError(Exception):
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


def bytes_to_unit(nbytes: int, *, color: bool = True) -> Optional[str]:
    if nbytes < 1000:
        return None

    ndec = decimal.Decimal(nbytes)
    if nbytes < 1_000_000:
        n = ndec / 1_000
        unit = "KB"
    elif nbytes < 1_000_000_000:
        n = ndec / 1_000_000
        unit = "MB"
    else:
        n = ndec / 1_000_000_000
        unit = "GB"

    nr = round(n, 1)
    if color:
        return f"{colors.number(nr)} {unit}"
    else:
        return f"{nr} {unit}"


def plural(n: int, s: str, ss: str = "", color: bool = False) -> str:
    if not ss:
        ss = s + "s"

    n_s = f"{n:,}"
    if color:
        n_s = colors.number(n_s)

    return f"{n_s} {s}" if n == 1 else f"{n_s} {ss}"


def err_and_bail(msg: Any) -> NoReturn:
    print(f"{colors.danger('error:')} {msg}", file=sys.stderr)
    sys.exit(1)
