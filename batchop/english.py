from typing import List

from . import colors
from .common import BatchOpError, bytes_to_unit, plural
from .db import Invocation, InvocationOp


def confirm_delete_n_files(nfiles: int, ndirs: int, nbytes: int) -> str:
    s1 = plural(nfiles, "file", color=True)
    s2 = plural(ndirs, "directory", "directories", color=True)

    s3 = plural(nbytes, "byte", color=True)
    human_readable = bytes_to_unit(nbytes)
    if human_readable is not None:
        s3 = f"{s3} ({human_readable})"

    if nfiles > 0:
        if ndirs > 0:
            return f"Delete {s1} and {s2} totaling {s3}? "
        else:
            return f"Delete {s1} totaling {s3}? "
    else:
        if ndirs > 0:
            return f"Delete {s2} totaling {s3}? "
        else:
            raise ValueError


def confirm_rename_n_files(nfiles: int) -> str:
    # TODO: give more information
    s1 = plural(nfiles, "file", color=True)
    return f"Rename {s1}? "


def confirm_undo(invocation: Invocation, ops: List[InvocationOp]) -> str:
    # assumption: `ops` is not empty
    # TODO: handle empty cmdline
    # TODO: show time command was run and warn if it was a while ago
    s1 = plural(len(ops), "op", color=True)
    return f"Undo `{colors.code(invocation.cmdline)}` command with {s1}? "
