import argparse
import os
import re
import subprocess
from pathlib import Path
from typing import Dict, Generator, List, Optional, Sequence, Union

from . import (
    colors,
    confirmation,
    english,
    exceptions,
    globreplace,
    parsing,
    __version__,
)
from .common import PathLike, err_and_bail, plural
from .db import (
    Database,
    InvocationOp,
    INVOCATION_CONTEXT_CLI,
    INVOCATION_CONTEXT_PYTHON,
    OP_TYPE_DELETE,
    OP_TYPE_RENAME,
    InvocationId,
    OpType,
    OP_TYPE_MOVE,
    OP_TYPE_CREATE,
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
) -> None:
    if directory is not None:
        os.chdir(directory)

    root = Path(".").absolute()
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
            raise exceptions.SyntaxUnknownCommand(parsed_cmd.command)
    elif isinstance(parsed_cmd, parsing.SpecialCommand):
        if parsed_cmd.command == "undo":
            bop.undo(require_confirm=require_confirm)
        else:
            raise exceptions.SyntaxUnknownCommand(parsed_cmd.command)
    elif isinstance(parsed_cmd, parsing.RenameCommand):
        fileset = FileSet(root, special_files=special_files)
        fileset.optimize()
        bop.rename(
            fileset,
            parsed_cmd.old,
            parsed_cmd.new,
            dry_run=dry_run,
            require_confirm=require_confirm,
            original_cmdline=original_cmdline,
        )
    elif isinstance(parsed_cmd, parsing.MoveCommand):
        fileset = FileSet(root, parsed_cmd.filters, special_files=special_files)
        fileset.optimize()
        bop.move(
            fileset,
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
                    f"{colors.danger('error:')} unknown directive: {cmd!r} (enter !help to see available directives)"
                )

            continue

        try:
            tokens = parsing.tokenize(s)
            filters = parsing.parse_preds(tokens, cwd=root)
        except exceptions.Base as e:
            print(f"{colors.danger('error:')} {e.fancy()}")
            continue

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
        if size.is_empty():
            raise exceptions.EmptyFileSet

        if require_confirm and not confirmation.confirm_operation_on_fileset(
            fileset, "Delete"
        ):
            print("Aborted.")
            return

        undo_mgr = UndoManager.start(
            self.db, self.directory / self._BACKUP_DIR, original_cmdline
        )
        for p in fileset.resolve(recurse=RecurseBehavior.EXCLUDE_DIR_CHILDREN):
            if dry_run:
                print(f"remove {p}")
            else:
                new_path = undo_mgr.add_op(OP_TYPE_DELETE, p)
                # TODO: any way to do this in batches?
                # TODO: cross-platform
                sh(["mv", p, new_path])

        if dry_run:
            self._dry_run_notice()

    def undo(self, *, require_confirm: bool = True) -> None:
        invocation, invocation_ops = self.db.get_last_invocation()

        if invocation is None:
            raise exceptions.Base("there is no previous command to undo")

        if invocation.cmdline:
            the_last_command = f"the last command ({invocation.cmdline!r})"
        else:
            the_last_command = "the last command"

        if not invocation.undoable:
            if invocation.cmdline:
                raise exceptions.Base(f"{the_last_command} was not undo-able")
            else:
                raise exceptions.Base(f"the last command was not undo-able")
        if len(invocation_ops) == 0:
            # TODO: is this case ever possible?
            raise exceptions.Base(
                f"{the_last_command} did not do anything so there is nothing to undo"
            )

        prompt = english.confirm_undo(invocation, invocation_ops)
        if require_confirm and not confirm(prompt):
            print("Aborted.")
            return

        # It is VERY important to sequence the undo ops correctly.
        #
        # Example:
        #   create A
        #   move B.txt to A
        #
        # If we undo create A before we undo the move, we deleted A/b.txt and now we can't restore it!
        #
        # In reality `_undo_create` will refuse to delete a non-empty directory. Still, the principle is important.
        _sort_undo_ops(invocation_ops)

        for op in invocation_ops:
            if op.op_type == OP_TYPE_DELETE:
                self._undo_delete(op)
            elif op.op_type == OP_TYPE_RENAME or op.op_type == OP_TYPE_MOVE:
                self._undo_rename_or_move(op)
            elif op.op_type == OP_TYPE_CREATE:
                self._undo_create(op)
            else:
                raise exceptions.Impossible

        self.db.delete_invocation(invocation.invocation_id)

    def _undo_delete(self, op: InvocationOp) -> None:
        if op.path_after.exists():
            # TODO: check for collision?
            # TODO: cross-platform
            sh(["mv", op.path_after, op.path_before])

        # TODO: what to do if path_after doesn't exist?
        # could be innocuous, e.g. previous 'undo' command failed midway but some paths were already
        # restored

    def _undo_rename_or_move(self, op: InvocationOp) -> None:
        if op.path_after.exists():
            # TODO: check for collision?
            # TODO: cross-platform
            sh(["mv", op.path_after, op.path_before])

    def _undo_create(self, op: InvocationOp) -> None:
        if op.path_after.exists():
            if op.path_after.is_dir():
                op.path_after.rmdir()
            else:
                op.path_after.unlink()
        # TODO: what to do if path_after doesn't exist?

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

        if require_confirm and not confirmation.confirm_operation_on_fileset(
            fileset, "Rename"
        ):
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

    def move(
        self,
        fileset: FileSet,
        destination_like: PathLike,
        *,
        dry_run: bool = False,
        require_confirm: bool = True,
        original_cmdline: str = "",
    ) -> None:
        destination = Path(destination_like).absolute()

        if require_confirm and not confirmation.confirm_operation_on_fileset(
            fileset, "Move"
        ):
            print("Aborted.")
            return

        paths_to_move = list(
            fileset.resolve(recurse=RecurseBehavior.EXCLUDE_DIR_CHILDREN)
        )

        _detect_duplicates(paths_to_move)

        if dry_run:
            for p in paths_to_move:
                print(f"move {p} to {destination}")
            self._dry_run_notice()
        else:
            undo_mgr = UndoManager.start(
                self.db, self.directory / self._BACKUP_DIR, original_cmdline
            )

            # TODO: add to confirmation message if destination will be created
            # TODO: register with undo manager
            # it is important to do this AFTER calling `fileset.resolve()` as otherwise the destination directory could
            # be picked up as a source
            undo_mgr.add_op(OP_TYPE_CREATE, None, destination)
            destination.mkdir(parents=False, exist_ok=True)

            for p in paths_to_move:
                undo_mgr.add_op(OP_TYPE_MOVE, p, destination / p.name)
            # TODO: pass `paths_to_move` in batches if really long
            sh(["mv"] + paths_to_move + [destination])

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
        self,
        op_type: OpType,
        path_before: Optional[Path],
        path_after: Optional[Path] = None,
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


def _sort_undo_ops(ops: List[InvocationOp]) -> None:
    def _key(op: InvocationOp) -> int:
        if op.op_type == OP_TYPE_CREATE:
            return 2
        else:
            return 1

    ops.sort(key=_key)


def _detect_duplicates(paths: List[Path]) -> None:
    already_seen: Dict[str, Path] = {}
    for path in paths:
        other = already_seen.get(path.name)
        if other is not None:
            raise exceptions.PathCollision(path1=path, path2=other)
        already_seen[path.name] = path


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
