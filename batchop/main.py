import argparse
import os
import shlex
import sys
from pathlib import Path
from typing import List

from . import colors, exceptions, parsing, __version__
from .batchop import BatchOp
from .common import err_and_bail, plural
from .db import INVOCATION_CONTEXT_CLI
from .fileset import FileSet, FilterSet


def main() -> None:
    _main(sys.argv[1:])


def _main(argv: List[str]) -> None:
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
        "--no-color", action="store_true", help="Turn off colored output."
    )
    parser.add_argument("--sort", action="store_true")
    parser.add_argument("--context", default=INVOCATION_CONTEXT_CLI)
    parser.add_argument("--version", action="version", version=__version__)

    subparsers = parser.add_subparsers()

    parser_count = add_subparser(subparsers, "count")
    parser_count.add_argument("words", nargs="+")

    parser_ls = add_subparser(subparsers, "ls")
    parser_ls.add_argument("words", nargs="+")

    parser_mv = add_subparser(subparsers, "mv")
    parser_mv.add_argument("files", nargs="*")
    parser_mv.add_argument("-q", "--query")
    parser_mv.add_argument("-t", "--to")

    parser_rename = add_subparser(subparsers, "rename")
    parser_rename.add_argument("old", help="glob pattern to match")
    parser_rename.add_argument("-t", "--to", help="pattern to substitute")

    add_subparser(subparsers, "repl")

    parser_rm = add_subparser(subparsers, "rm")
    parser_rm.add_argument("files", nargs="*")
    parser_rm.add_argument("-q", "--query")

    add_subparser(subparsers, "undo")

    args = parser.parse_args(argv)

    if args.directory:
        os.chdir(args.directory)

    root = Path(".").absolute()
    require_confirm = not args.no_confirm

    if not hasattr(args, "subcommand"):
        parser.print_help()
        return

    # https://no-color.org/
    if args.no_color or os.environ.get("NO_COLOR"):
        colors.disable()

    try:
        bop = BatchOp(root, context=args.context)
        if args.subcommand == "count":
            main_count(bop, args.words)
        elif args.subcommand == "ls":
            main_ls(bop, args.words, sort=args.sort)
        elif args.subcommand == "mv":
            if args.to:
                destination = args.to
            else:
                if len(args.files) < 2:
                    err_and_bail("no destination specified for 'mv' command")

                destination = args.files.pop()

            main_mv(
                bop,
                args.files,
                destination,
                query=args.query,
                require_confirm=require_confirm,
                dry_run=args.dry_run,
            )
        elif args.subcommand == "rename":
            main_rename(
                bop,
                args.old,
                args.to,
                require_confirm=require_confirm,
                dry_run=args.dry_run,
            )
        elif args.subcommand == "repl":
            main_repl(dry_run=args.dry_run)
        elif args.subcommand == "rm":
            main_rm(
                bop,
                args.files,
                query=args.query,
                require_confirm=require_confirm,
                dry_run=args.dry_run,
            )
        elif args.subcommand == "undo":
            # TODO: dry_run?
            main_undo(bop, require_confirm=require_confirm)
        else:
            raise exceptions.Impossible
    except exceptions.Base as e:
        err_and_bail(e.fancy())


def add_subparser(subparsers, name):
    p = subparsers.add_parser(name)
    p.set_defaults(subcommand=name)
    return p


def main_count(bop: BatchOp, words: List[str]) -> None:
    filterset = parsing.parse_query(" ".join(words))
    print(bop.count(filterset))


def main_ls(bop: BatchOp, words: List[str], *, sort: bool = False) -> None:
    filterset = parsing.parse_query(" ".join(words))

    paths = bop.list(filterset)
    if sort:
        paths.sort()

    for p in paths:
        print(p.relative_to(bop.root))


def main_mv(
    bop: BatchOp,
    files: List[str],
    destination: str,
    *,
    query: str = "",
    require_confirm: bool,
    dry_run: bool,
) -> None:
    filterset = _check_files_and_query(files, query)

    if query:
        original_cmdline = f"mv {shlex.quote(query)}"
    else:
        original_cmdline = f"mv {' '.join(map(shlex.quote, files))}"

    bop.move(
        filterset,
        destination,
        require_confirm=require_confirm,
        dry_run=dry_run,
        original_cmdline=original_cmdline,
    )


def main_rename(
    bop: BatchOp, old: str, new: str, *, require_confirm: bool, dry_run: bool
) -> None:
    original_cmdline = f"rename {shlex.quote(old)} {shlex.quote(new)}"
    bop.rename(
        old,
        new,
        require_confirm=require_confirm,
        dry_run=dry_run,
        original_cmdline=original_cmdline,
    )


def main_rm(
    bop: BatchOp, files: List[str], *, query: str, require_confirm: bool, dry_run: bool
) -> None:
    filterset = _check_files_and_query(files, query)

    if query:
        original_cmdline = f"rm {shlex.quote(query)}"
    else:
        original_cmdline = f"rm {' '.join(map(shlex.quote, files))}"

    bop.delete(
        filterset,
        require_confirm=require_confirm,
        dry_run=dry_run,
        original_cmdline=original_cmdline,
    )


def main_undo(bop: BatchOp, *, require_confirm: bool) -> None:
    bop.undo(require_confirm=require_confirm)


def main_repl(*, dry_run: bool = False) -> None:
    import readline  # noqa: F401

    root = Path(".").absolute()
    filterset = FilterSet().is_not_hidden()

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


def _check_files_and_query(files: List[str], query: str) -> FilterSet:
    # TODO: better error messages
    if files and query:
        err_and_bail("both files and query (-q) cannot be provided")

    if files:
        return FilterSet().is_exactly(files)
    elif query:
        return parsing.parse_query(query)
    else:
        err_and_bail("either files or query (-q) must be provided")
