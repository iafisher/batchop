"""
Supported operations:

- delete <fileset>
- rename <pattern1> <pattern2>
- move <fileset> <destination>
- list <fileset>
- replace <pattern1> <pattern2> <fileset>
- run <cmd> <fileset>

Python interface:

    bop = BatchOp()
    bop.delete(FileSet().is_empty().is_folder().is_named("Archive"))

Command-line interface:

    $ batchop 'delete all folders named "Archive" that are not empty'
    $ batchop 'rename %_trip.jpg to %.jpg'

Interactive interface:

    $ batchop
    671 files, 17 folders
    > is a file
    671 files
    > ends with .md
    534 files
    > move to markdown-files

"""

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Generator, List, Optional, Union

from . import filters, parsing
from .common import BatchOpSyntaxError, PathLike
from .fileset import FileSet
from .filters import Filter


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--directory")
    parser.add_argument("words", nargs="*")
    args = parser.parse_args()

    if len(args.words) > 0:
        cmdstr = " ".join(args.words)
        main_execute(cmdstr, directory=args.directory)
    else:
        main_interactive(args.directory)


def main_execute(cmdstr: str, *, directory: Optional[str]) -> None:
    try:
        parsed_cmd = parsing.parse_command(cmdstr)
    except BatchOpSyntaxError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)

    bop = BatchOp()
    fileset = FileSet(path_or_default(directory), parsed_cmd.filters)
    if parsed_cmd.command == "delete":
        bop.delete(fileset)
    elif parsed_cmd.command == "list":
        for p in bop.list(fileset):
            print(p)
    elif parsed_cmd.command == "count":
        n = bop.count(fileset)
        print(n)
    else:
        parsing.err_unknown_command(parsed_cmd.command)


def main_interactive(d: Optional[str]) -> None:
    import readline

    root = path_or_default(d)
    fs = FileSet.with_default_filters(root)
    if len(fs.filters) > 0:
        print("Filters applied by default: ")
        for f in fs.filters:
            print(f"  {f}")
        print()

    # whether to re-calculate the file set on next iteration of loop
    recalculate = True
    current_files = []
    while True:
        # TODO: separate counts for files and directories
        # TODO: default to ignoring .git + .gitignore?
        if recalculate:
            current_files = list(fs.resolve())
            print(f"{plural(len(current_files), 'file')}")

        recalculate = False
        try:
            s = input("> ").strip()
        except BatchOpSyntaxError as e:
            print(f"error: {e}")
            continue
        except EOFError:
            print()
            break

        if not s:
            continue

        if s.lower() == "list":
            for p in current_files:
                print(p)
            continue
        elif s[0] == "!":
            cmd = s[1:]
            if cmd == "pop":
                fs.pop()
                recalculate = True
            elif cmd == "clear":
                fs.clear()
                recalculate = True
            elif cmd == "filter" or cmd == "filters":
                for f in fs.filters:
                    print(f)
            elif cmd == "h" or cmd == "help":
                print("Directives:")
                print("  !clear              clear all filters")
                print("  !filter/!filters    print list of current filters")
                print("  !pop                remove the last-applied filter")
            else:
                print(
                    f"error: unknown directive: {cmd!r} (enter !help to see available directives)"
                )

            continue

        tokens = parsing.tokenize(s)
        filters = parsing.parse_preds(tokens)
        fs.filters.extend(filters)
        recalculate = True


class BatchOp:
    def list(self, fileset: FileSet) -> Generator[Path, None, None]:
        yield from list(fileset.resolve())

    def count(self, fileset: FileSet) -> int:
        return sum(1 for _ in fileset.resolve())

    def delete(self, fileset: FileSet) -> None:
        # TODO: avoid computing entire file-set twice?
        size = fileset.calculate_size()
        nfiles = size.file_count
        ndirs = size.directory_count
        nbytes = size.size_in_bytes
        # TODO: don't print counts if 0
        # TODO: human-readable size units
        # TODO: option to list files
        # TODO: use `du` command if available
        prompt = (
            f"Delete {plural(nfiles, 'file')} and {plural(ndirs, 'folder')} "
            + f"totaling {plural(nbytes, 'byte')}? "
        )
        if not confirm(prompt):
            print("Aborted.")
            return

        # TODO: don't remove files that are in a directory that will be removed
        # TODO: don't use -rf except for directories
        # TODO: pass paths to `rm` in batches
        for p in fileset.resolve():
            # TODO: enable rm
            sh(["echo", "rm", "-rf", str(p)])


def sh(args: List[str]) -> None:
    subprocess.run(args, capture_output=True, check=True)


def confirm(prompt: str) -> bool:
    while True:
        r = input(prompt).strip().lower()
        if r == "yes" or r == "y":
            return True
        elif r == "no" or r == "n":
            return False
        else:
            print("Please enter 'yes' or 'no'.")


def path_or_default(p: Optional[PathLike]) -> Path:
    if p is None:
        r = Path(".")
    elif isinstance(p, Path):
        r = p
    else:
        r = Path(p)

    return r


def plural(n: int, s: str) -> str:
    return f"{n} {s}" if n == 1 else f"{n} {s}s"
