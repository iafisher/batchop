import decimal
import re
from pathlib import Path
from typing import Optional, Union


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
