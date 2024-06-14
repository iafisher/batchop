import argparse
import os
import re
import subprocess
from pathlib import Path
from typing import Generator, List, Optional, Sequence, Union

from . import english, globreplace, parsing, __version__
from .common import (
    BatchOpError,
    BatchOpImpossibleError,
    BatchOpSyntaxError,
    PathLike,
    err_and_bail,
    plural,
)
from .db import (
    Database,
    InvocationOp,
    INVOCATION_CONTEXT_CLI,
    INVOCATION_CONTEXT_PYTHON,
    OP_TYPE_DELETE,
    OP_TYPE_RENAME,
    InvocationId,
    OpType,
)
from .fileset import FileSet, RecurseBehavior


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
    except BatchOpError as e:
        err_and_bail(e)


def main_execute(
    words: Union[str, List[str]],
    *,
    directory: Optional[str],
    require_confirm: bool,
    dry_run: bool = False,
    special_files: bool = False,
    context: str = INVOCATION_CONTEXT_CLI,
) -> None:
    root = path_or_default(directory).absolute()
    original_cmdline = words if isinstance(words, str) else " ".join(words)
    parsed_cmd = parsing.parse_command(words, cwd=root)

    bop = BatchOp(context=context)
    if isinstance(parsed_cmd, parsing.UnaryCommand):
        fileset = FileSet(root, parsed_cmd.filters, special_files=special_files)
        fileset.optimize()
        if parsed_cmd.command == "delete":
            bop.delete(
                fileset,
                dry_run=dry_run,
                require_confirm=require_confirm,
                original_cmdline=original_cmdline,
            )
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
    elif isinstance(parsed_cmd, parsing.SpecialCommand):
        if parsed_cmd.command == "undo":
            bop.undo(require_confirm=require_confirm)
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
            original_cmdline=original_cmdline,
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
    # this is BatchOp's bookkeeping directory, not the directory the user is querying
    directory: Path
    db: Database

    _BACKUP_DIR = "backup"

    def __init__(self, *, context: str = INVOCATION_CONTEXT_PYTHON) -> None:
        self.directory = self._ensure_directory()
        self.db = Database(self.directory, context=context)
        self.db.create_tables()

    def list(self, fileset: FileSet) -> Generator[Path, None, None]:
        yield from list(fileset.resolve())

    def count(self, fileset: FileSet) -> int:
        return sum(1 for _ in fileset.resolve())

    def delete(
        self,
        fileset: FileSet,
        *,
        dry_run: bool = False,
        require_confirm: bool = True,
        original_cmdline: str = "",
    ) -> None:
        # TODO: avoid computing entire file-set twice?
        # TODO: use `du` command if available
        size = fileset.calculate_size(recurse=RecurseBehavior.INCLUDE_DIR_CHILDREN)
        nfiles = size.file_count
        ndirs = size.directory_count
        nbytes = size.size_in_bytes

        if nfiles == 0 and ndirs == 0:
            raise BatchOpError("nothing to delete")

        # TODO: option to list files
        prompt = english.confirm_delete_n_files(nfiles, ndirs, nbytes)
        if require_confirm and not confirm(prompt):
            print("Aborted.")
            return

        undo_mgr = UndoManager.start(
            self.db, self.directory / self._BACKUP_DIR, original_cmdline
        )
        for p in fileset.resolve(recurse=RecurseBehavior.EXCLUDE_DIR_CHILDREN):
            if dry_run:
                print("remove {p}")
            else:
                new_path = undo_mgr.add_op(OP_TYPE_DELETE, p)
                # TODO: any way to do this in batches?
                # TODO: cross-platform
                sh(["mv", p, new_path])

        if dry_run:
            self._dry_run_notice()

    def undo(self, *, require_confirm: bool = True) -> None:
        # TODO: confirmation

        invocation, invocation_ops = self.db.get_last_invocation()
        if invocation is None:
            # TODO: better message
            raise BatchOpError("no previous command found")
        if not invocation.undoable:
            # TODO: better message
            raise BatchOpError("last command was not undo-able")
        if len(invocation_ops) == 0:
            # TODO: better message
            raise BatchOpError("nothing to undo")

        prompt = english.confirm_undo(invocation, invocation_ops)
        if require_confirm and not confirm(prompt):
            print("Aborted.")
            return

        for op in invocation_ops:
            if op.op_type == OP_TYPE_DELETE:
                self._undo_delete(op)
            elif op.op_type == OP_TYPE_RENAME:
                self._undo_rename(op)
            else:
                raise BatchOpImpossibleError

        self.db.delete_invocation(invocation.invocation_id)

    def _undo_delete(self, op: InvocationOp) -> None:
        if op.path_after.exists():
            # TODO: check for collision?
            sh(["mv", op.path_after, op.path_before])

        # TODO: what to do if path_after doesn't exist?
        # could be innocuous, e.g. previous 'undo' command failed midway but some paths were already
        # restored

    def _undo_rename(self, op: InvocationOp) -> None:
        if op.path_after.exists():
            # TODO: check for collision?
            sh(["mv", op.path_after, op.path_before])

    def rename(
        self,
        fileset: FileSet,
        old: str,
        new: str,
        *,
        dry_run: bool = False,
        require_confirm: bool = True,
        original_cmdline: str = "",
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

        undo_mgr = UndoManager.start(
            self.db, self.directory / self._BACKUP_DIR, original_cmdline
        )
        for p in fileset.resolve():
            new_name = pattern.sub(repl, p.name)
            if new_name == p.name:
                continue

            if dry_run:
                print(f"rename {p} to {new_name}")
            else:
                new_path = p.parent / new_name
                undo_mgr.add_op(OP_TYPE_RENAME, p, new_path)
                # TODO: cross-platform
                sh(["mv", "-n", p, new_path])

        if dry_run:
            self._dry_run_notice()

    def _dry_run_notice(self):
        print()
        print("Dry run: no files changed.")

    @classmethod
    def _ensure_directory(cls) -> Path:
        d = cls._choose_directory()
        d.mkdir(exist_ok=True)
        (d / cls._BACKUP_DIR).mkdir(exist_ok=True)
        return d

    @classmethod
    def _choose_directory(cls) -> Path:
        # TODO: check permissions
        env_batch_dir = os.environ.get("BATCHOP_DIR")
        if env_batch_dir is not None:
            return Path(env_batch_dir).absolute()

        env_xdg_data_home = os.environ.get("XDG_DATA_HOME")
        if env_xdg_data_home is not None:
            return Path(env_xdg_data_home).absolute() / "batchop"

        local_share = Path.home() / ".local" / "share"
        if local_share.exists() and local_share.is_dir():
            return local_share / "batchop"

        return Path.home() / ".batchop"


class UndoManager:
    db: Database
    backup_directory: Path
    invocation_id: InvocationId
    i: int

    @classmethod
    def start(cls, db: Database, backup_directory: Path, cmdline: str) -> "UndoManager":
        invocation_id = db.create_invocation(cmdline, undoable=True)
        return cls(db, backup_directory, invocation_id)

    # call `start`, don't call `__init__` directly
    def __init__(
        self, db: Database, backup_directory: Path, invocation_id: InvocationId
    ) -> None:
        self.db = db
        self.backup_directory = backup_directory
        self.invocation_id = invocation_id
        self.i = 1

    def add_op(
        self, op_type: OpType, path_before: Path, path_after: Optional[Path] = None
    ) -> Path:
        if path_after is None:
            path_after = self._make_new_path()

        self.db.create_invocation_op(
            self.invocation_id, op_type, path_before, path_after
        )
        return path_after

    def _make_new_path(self) -> Path:
        r = self.backup_directory / f"{self.invocation_id}___{self.i:0>8}"
        self.i += 1
        return r


def sh(args: Sequence[Union[str, Path]]) -> None:
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
