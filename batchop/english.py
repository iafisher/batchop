from typing import List

from . import colors, exceptions
from .common import bytes_to_unit, plural
from .db import Invocation, InvocationOp
from .fileset import FileSetSize


def confirm_delete_n_files(size: FileSetSize) -> str:
    return _confirm_n_files_generic("Delete", size)


def confirm_rename_n_files(size: FileSetSize) -> str:
    # TODO: give more information
    s1 = plural(size.file_count, "file", color=True)
    return f"Rename {s1}? "


def confirm_move_n_files(size: FileSetSize) -> str:
    return _confirm_n_files_generic("Move", size)


def _confirm_n_files_generic(verb: str, size: FileSetSize) -> str:
    s1 = plural(size.file_count, "file", color=True)
    s2 = plural(size.directory_count, "directory", "directories", color=True)

    s3 = plural(size.size_in_bytes, "byte", color=True)
    human_readable = bytes_to_unit(size.size_in_bytes)
    if human_readable is not None:
        s3 = f"{s3} ({human_readable})"

    if size.file_count > 0:
        if size.directory_count > 0:
            return f"{verb} {s1} and {s2} totaling {s3}? "
        else:
            return f"{verb} {s1} totaling {s3}? "
    else:
        if size.directory_count > 0:
            return f"{verb} {s2} totaling {s3}? "
        else:
            raise exceptions.Impossible


def confirm_undo(invocation: Invocation, ops: List[InvocationOp]) -> str:
    # assumption: `ops` is not empty
    # TODO: handle empty cmdline
    # TODO: show time command was run and warn if it was a while ago
    s1 = plural(len(ops), "op", color=True)
    return f"Undo `{colors.code(invocation.cmdline)}` command with {s1}? "
