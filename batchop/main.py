import argparse
import os
from pathlib import Path
from typing import Iterable, List, Optional, Union

from . import colors, exceptions, parsing, __version__
from .batchop import BatchOp
from .common import PathLike, err_and_bail, plural
from .db import INVOCATION_CONTEXT_CLI
from .fileset import FileSet, FilterSet


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
    parser.add_argument("--version", action="version", version=__version__)
    args = parser.parse_args()

    try:
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
    except exceptions.Base as e:
        err_and_bail(e.fancy())


def main_execute(
    words: Union[str, List[str]],
    *,
    directory: Optional[str],
    require_confirm: bool,
    dry_run: bool = False,
    special_files: bool = False,
    context: str = INVOCATION_CONTEXT_CLI,
    sort_output: bool = False,
) -> None:
    if directory is not None:
        os.chdir(directory)

    root = Path(".").absolute()
    original_cmdline = words if isinstance(words, str) else " ".join(words)
    parsed_cmd = parsing.parse_command(words)

    bop = BatchOp(context=context)
    if isinstance(parsed_cmd, parsing.UnaryCommand):
        filterset = FilterSet(parsed_cmd.filters, special_files=special_files)
        # filterset.optimize()
        if parsed_cmd.command == "delete":
            bop.delete(
                filterset,
                dry_run=dry_run,
                require_confirm=require_confirm,
                original_cmdline=original_cmdline,
            )
        elif parsed_cmd.command == "list":
            it: Iterable[Path] = bop.list(filterset)
            if sort_output:
                it = sorted(it)

            for p in it:
                print(p.relative_to(root))
        elif parsed_cmd.command == "count":
            n = bop.count(filterset)
            print(n)
        else:
            raise exceptions.SyntaxUnknownCommand(parsed_cmd.command)
    elif isinstance(parsed_cmd, parsing.SpecialCommand):
        if parsed_cmd.command == "undo":
            bop.undo(require_confirm=require_confirm)
        else:
            raise exceptions.SyntaxUnknownCommand(parsed_cmd.command)
    elif isinstance(parsed_cmd, parsing.RenameCommand):
        filterset = FilterSet(special_files=special_files)
        # filterset.optimize()
        bop.rename(
            filterset,
            parsed_cmd.old,
            parsed_cmd.new,
            dry_run=dry_run,
            require_confirm=require_confirm,
            original_cmdline=original_cmdline,
        )
    elif isinstance(parsed_cmd, parsing.MoveCommand):
        filterset = FilterSet(parsed_cmd.filters, special_files=special_files)
        # filterset.optimize()
        bop.move(
            filterset,
            parsed_cmd.destination,
            dry_run=dry_run,
            require_confirm=require_confirm,
            original_cmdline=original_cmdline,
        )
    else:
        raise exceptions.Impossible


def main_interactive(
    d: Optional[str], *, dry_run: bool = False, special_files: bool = False
) -> None:
    import readline

    root = path_or_default(d).absolute()
    filterset = FilterSet(special_files=special_files).is_not_hidden()

    if len(filterset.get_filters()) > 0:
        print("Filters applied by default: ")
        for f in filterset.get_filters():
            print(f"  {f}")
        print()

    # whether to re-calculate the file set on next iteration of loop
    recalculate = True
    fileset = FileSet([])
    while True:
        # TODO: default to ignoring .git + .gitignore?
        if recalculate:
            fileset = filterset.resolve(root, recursive=False)
            print(f"{plural(fileset.file_count(), 'file', color=True)}", end="")

            dir_count = fileset.dir_count()
            if dir_count > 0:
                print(f", {plural(dir_count, 'directory', 'directories', color=True)}")
            else:
                print()

        recalculate = False
        try:
            s = input("> ").strip()
        except exceptions.Syntax as e:
            print(f"error: {e}")
            continue
        except EOFError:
            print()
            break

        if not s:
            continue

        # TODO: other commands (and respect --dry-run)
        if s.lower() == "list":
            for p in fileset:
                print(p)
            continue
        elif s[0] == "!":
            cmd = s[1:]
            if cmd == "pop":
                filterset.pop()
                recalculate = True
            elif cmd == "clear":
                filterset.clear()
                recalculate = True
            elif cmd == "filter" or cmd == "filters":
                for f in filterset.get_filters():
                    print(f)
            elif cmd == "h" or cmd == "help":
                print("Directives:")
                print("  !clear              clear all filters")
                print("  !filter/!filters    print list of current filters")
                print("  !pop                remove the last-applied filter")
            else:
                print(
                    f"{colors.danger('error:')} unknown directive: {cmd!r} (enter !help to see available directives)"
                )

            continue

        try:
            tokens = parsing.tokenize(s)
            filters = parsing.parse_preds(tokens)
        except exceptions.Base as e:
            print(f"{colors.danger('error:')} {e.fancy()}")
            continue

        filterset.extend(filters)
        recalculate = True


def path_or_default(p: Optional[PathLike]) -> Path:
    if p is None:
        r = Path(".")
    elif isinstance(p, Path):
        r = p
    else:
        r = Path(p)

    return r
