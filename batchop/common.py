from pathlib import Path
from typing import Union


class BatchOpError(Exception):
    pass


class BatchOpSyntaxError(BatchOpError):
    pass


class BatchOpImpossibleError(BatchOpError):
    pass


PathLike = Union[str, Path]
