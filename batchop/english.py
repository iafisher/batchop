from typing import List

from . import colors, exceptions
from .common import bytes_to_unit, plural
from .db import Invocation, InvocationOp
from .fileset import FileSet


def confirm_n_files_generic(verb: str, fs: FileSet) -> str:
    file_count = fs.file_count()
    dir_count = fs.dir_count()
    size_bytes = fs.size_bytes()

    s1 = plural(file_count, "file", color=True)
    s2 = plural(dir_count, "directory", "directories", color=True)

    s3 = plural(size_bytes, "byte", color=True)
    human_readable = bytes_to_unit(size_bytes)
    if human_readable is not None:
        s3 = f"{s3} ({human_readable})"

    if file_count > 0:
        if dir_count > 0:
            return f"{verb} {s1} and {s2} totaling {s3}? "
        else:
            return f"{verb} {s1} totaling {s3}? "
    else:
        if dir_count > 0:
            return f"{verb} {s2} totaling {s3}? "
        else:
            raise exceptions.Impossible


def confirm_undo(invocation: Invocation, ops: List[InvocationOp]) -> str:
    # assumption: `ops` is not empty
    # TODO: handle empty cmdline
    # TODO: show time command was run and warn if it was a while ago
    s1 = plural(len(ops), "op", color=True)
    return f"Undo `{colors.code(invocation.cmdline)}` command with {s1}? "
