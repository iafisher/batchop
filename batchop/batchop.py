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
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Generator, List, Optional, Sequence, Union

from . import colors, english, filters, globreplace, parsing
from .common import BatchOpImpossibleError, BatchOpSyntaxError, PathLike, plural
from .fileset import FileSet, RecurseBehavior
from .filters import Filter


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--directory")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what the command would do without doing it.",
    )
    parser.add_argument(
        "--no-confirm",
        action="store_true",
        help="Execute the command without confirmation. Not recommended.",
    )
    parser.add_argument(
        "--special-files",
        action="store_true",
        help="Include files that are neither regular files nor directories. This is rarely desirable.",
    )
    parser.add_argument("words", nargs="*")
    args = parser.parse_args()

    if len(args.words) > 0:
        words = args.words[0] if len(args.words) == 1 else args.words
        main_execute(
            words,
            directory=args.directory,
            dry_run=args.dry_run,
            require_confirm=not args.no_confirm,
            special_files=args.special_files,
        )
    else:
        main_interactive(
            args.directory, dry_run=args.dry_run, special_files=args.special_files
        )


def main_execute(
    words: Union[str, List[str]],
    *,
    directory: Optional[str],
    require_confirm: bool,
    dry_run: bool = False,
    special_files: bool = False,
) -> None:
    root = path_or_default(directory).absolute()

    try:
        parsed_cmd = parsing.parse_command(words, cwd=root)
    except BatchOpSyntaxError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)

    bop = BatchOp()
    if isinstance(parsed_cmd, parsing.UnaryCommand):
        fileset = FileSet(root, parsed_cmd.filters, special_files=special_files)
        if parsed_cmd.command == "delete":
            bop.delete(fileset, dry_run=dry_run, require_confirm=require_confirm)
        elif parsed_cmd.command == "list":
            cwd = Path(".").absolute()
            if fileset.root == cwd:
                for p in bop.list(fileset):
                    print(p.relative_to(cwd))
            else:
                for p in bop.list(fileset):
                    print(p)
        elif parsed_cmd.command == "count":
            n = bop.count(fileset)
            print(n)
        else:
            parsing.err_unknown_command(parsed_cmd.command)
    elif isinstance(parsed_cmd, parsing.RenameCommand):
        fileset = FileSet(path_or_default(directory), special_files=special_files)
        bop.rename(
            fileset,
            parsed_cmd.old,
            parsed_cmd.new,
            dry_run=dry_run,
            require_confirm=require_confirm,
        )
    else:
        raise BatchOpImpossibleError


def main_interactive(
    d: Optional[str], *, dry_run: bool = False, special_files: bool = False
) -> None:
    import readline

    root = path_or_default(d).absolute()
    fs = FileSet(root, special_files=special_files).is_not_hidden()

    if len(fs.filters) > 0:
        print("Filters applied by default: ")
        for f in fs.filters:
            print(f"  {f}")
        print()

    # whether to re-calculate the file set on next iteration of loop
    recalculate = True
    while True:
        # TODO: default to ignoring .git + .gitignore?
        if recalculate:
            size = fs.calculate_size()
            print(f"{plural(size.file_count, 'file', color=True)}", end="")
            if size.directory_count > 0:
                print(
                    f", {plural(size.directory_count, 'directory', 'directories', color=True)}"
                )
            else:
                print()

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

        # TODO: other commands (and respect --dry-run)
        if s.lower() == "list":
            for p in fs.resolve():
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
        filters = parsing.parse_preds(tokens, cwd=root)
        fs.filters.extend(filters)
        recalculate = True


class BatchOp:
    def list(self, fileset: FileSet) -> Generator[Path, None, None]:
        yield from list(fileset.resolve())

    def count(self, fileset: FileSet) -> int:
        return sum(1 for _ in fileset.resolve())

    def delete(
        self, fileset: FileSet, *, dry_run: bool = False, require_confirm: bool = True
    ) -> None:
        # TODO: avoid computing entire file-set twice?
        # TODO: use `du` command if available
        size = fileset.calculate_size(recurse=RecurseBehavior.INCLUDE_DIR_CHILDREN)
        nfiles = size.file_count
        ndirs = size.directory_count
        nbytes = size.size_in_bytes

        if nfiles == 0 and ndirs == 0:
            return

        # TODO: option to list files
        prompt = english.confirm_delete_n_files(nfiles, ndirs, nbytes)
        if require_confirm and not confirm(prompt):
            print("Aborted.")
            return

        # TODO: pass paths to `rm` in batches
        for p in fileset.resolve(recurse=RecurseBehavior.EXCLUDE_DIR_CHILDREN):
            # TODO: cross-platform
            if p.is_dir():
                sh(["rm", "-rf", p], dry_run=dry_run)
            else:
                sh(["rm", p], dry_run=dry_run)

    def rename(
        self,
        fileset: FileSet,
        old: str,
        new: str,
        *,
        dry_run: bool = False,
        require_confirm: bool = True,
    ) -> None:
        # TODO: detect name collisions
        pattern = re.compile(globreplace.glob_to_regex(old))
        repl = globreplace.glob_to_regex_repl(new)

        fileset = fileset.matches(pattern)

        size = fileset.calculate_size()
        nfiles = size.file_count
        if nfiles == 0:
            return

        if require_confirm and not confirm(english.confirm_rename_n_files(nfiles)):
            print("Aborted.")
            return

        for p in fileset.resolve():
            new_name = pattern.sub(repl, p.name)
            if new_name == p.name:
                continue

            # TODO: cross-platform
            sh(["mv", "-n", p, p.parent / new_name], dry_run=dry_run)


def sh(args: Sequence[Union[str, Path]], *, dry_run: bool = False) -> None:
    if dry_run:
        args = ["echo"] + list(args)

    # don't capture output when --dry-run so that `echo` prints to the terminal
    subprocess.run(args, capture_output=not dry_run, check=True)


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
