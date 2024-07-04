import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from . import confirmation, english, exceptions, globreplace
from .common import AbsolutePath, PathLike, abspath
from .db import (
    INVOCATION_CONTEXT_PYTHON,
    OP_TYPE_CREATE,
    OP_TYPE_DELETE,
    OP_TYPE_MOVE,
    OP_TYPE_RENAME,
    Database,
    InvocationId,
    InvocationOp,
    OpType,
)
from .fileset import FileSet, FilterSet


@dataclass
class DeleteResult:
    paths_deleted: List[AbsolutePath]


@dataclass
class MoveResult:
    paths_moved: List[AbsolutePath]
    destination: AbsolutePath


@dataclass
class RenameResult:
    paths_renamed: Dict[AbsolutePath, str]


@dataclass
class UndoResult:
    original_cmdline: str
    num_ops: int


class BatchOp:
    # this is the directory the user is querying
    root: AbsolutePath
    # this is BatchOp's bookkeeping directory
    directory: AbsolutePath
    db: Database

    def __init__(
        self, root: Optional[PathLike] = None, context: str = INVOCATION_CONTEXT_PYTHON
    ) -> None:
        if root is None:
            self.root = abspath(Path.cwd())
        else:
            self.root = abspath(root)

        self.directory = self._choose_directory()
        self.db = Database(self.directory, context=context)
        self.db.create_tables()

        self.directory.mkdir(exist_ok=True)
        self.backup_dir().mkdir(exist_ok=True)

    def count(self, filterset: FilterSet) -> int:
        fileset = filterset.resolve(self.root, recursive=False)
        return len(fileset)

    def delete(
        self,
        filterset: FilterSet,
        *,
        require_confirm: bool = True,
        dry_run: bool = False,
        original_cmdline: str = "",
    ) -> Optional[DeleteResult]:
        fileset = filterset.resolve(self.root, recursive=True)
        if fileset.is_empty():
            raise exceptions.EmptyFileSet

        if require_confirm:
            if not confirmation.confirm_operation_on_fileset(fileset, "Delete"):
                return None

        paths_deleted = []
        if dry_run:
            paths_deleted = list(fileset.exclude_children())
        else:
            undo_mgr = UndoManager.start(self.db, self.backup_dir(), original_cmdline)
            for p in fileset.exclude_children():
                new_path = undo_mgr.add_op(OP_TYPE_DELETE, p)
                shutil.move(p, new_path)
                paths_deleted.append(p)

        return DeleteResult(paths_deleted)

    def list(self, filterset: FilterSet) -> List[AbsolutePath]:
        return list(filterset.resolve(self.root, recursive=False))

    def move(
        self,
        filterset: FilterSet,
        destination_like: PathLike,
        *,
        require_confirm: bool = True,
        dry_run: bool = False,
        original_cmdline: str = "",
    ) -> Optional[MoveResult]:
        destination = abspath(destination_like, root=self.root)
        if destination.exists() and not destination.is_dir():
            raise exceptions.NotADirectory(destination)

        fileset = filterset.resolve(self.root, recursive=True)
        if fileset.is_empty():
            raise exceptions.EmptyFileSet

        if require_confirm:
            if not confirmation.confirm_operation_on_fileset(fileset, "Move"):
                return None

        _detect_duplicates(fileset)

        paths_moved = list(fileset)
        if not dry_run:
            undo_mgr = UndoManager.start(self.db, self.backup_dir(), original_cmdline)
            # TODO: add to confirmation message if destination will be created
            # it is important to do this AFTER calling `fileset.resolve()` as otherwise the destination directory could
            # be picked up as a source
            undo_mgr.add_op(OP_TYPE_CREATE, None, destination)
            destination.mkdir(parents=False, exist_ok=True)

            for p in paths_moved:
                undo_mgr.add_op(OP_TYPE_MOVE, p, destination / p.name)
                # TODO: do in batches?
                shutil.move(p, destination)

        return MoveResult(paths_moved, destination)

    def rename(
        self,
        old: str,
        new: str,
        *,
        filterset_opt: Optional[FilterSet] = None,
        require_confirm: bool = True,
        dry_run: bool = False,
        original_cmdline: str = "",
    ) -> Optional[RenameResult]:
        if filterset_opt is None:
            # TODO: FilterSet() is inefficient, should constrain based on `old` pattern
            filterset = FilterSet()
        else:
            filterset = filterset_opt

        pattern = re.compile(globreplace.glob_to_regex(old))
        repl = globreplace.glob_to_regex_repl(new)

        fileset = filterset.resolve(self.root, recursive=False)
        if fileset.is_empty():
            raise exceptions.EmptyFileSet

        if require_confirm:
            if not confirmation.confirm_operation_on_fileset(fileset, "Rename"):
                return None

        paths_renamed: Dict[AbsolutePath, str] = {}
        for p in fileset:
            new_name = pattern.sub(repl, p.name)
            if new_name == p.name:
                continue

            paths_renamed[p] = new_name

        _detect_name_collisions(paths_renamed)

        if not dry_run:
            # TODO: detect name collisions before starting
            undo_mgr = UndoManager.start(self.db, self.backup_dir(), original_cmdline)
            for p, new_name in paths_renamed.items():
                new_path = p.parent / new_name
                undo_mgr.add_op(OP_TYPE_RENAME, p, new_path)
                # TODO: don't overwrite existing
                shutil.move(p, new_path)

        return RenameResult(paths_renamed)

    # TODO: should this take an explicit undo ID?
    def undo(self, *, require_confirm: bool = True) -> Optional[UndoResult]:
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
        if require_confirm and not confirmation.confirm(prompt):
            return None

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
        return UndoResult(
            original_cmdline=invocation.cmdline, num_ops=len(invocation_ops)
        )

    def _undo_delete(self, op: InvocationOp) -> None:
        if op.path_after.exists():
            # TODO: check for collision?
            shutil.move(op.path_after, op.path_before)

        # TODO: what to do if path_after doesn't exist?
        # could be innocuous, e.g. previous 'undo' command failed midway but some paths were already
        # restored

    def _undo_rename_or_move(self, op: InvocationOp) -> None:
        if op.path_after.exists():
            # TODO: check for collision?
            shutil.move(op.path_after, op.path_before)

    def _undo_create(self, op: InvocationOp) -> None:
        if op.path_after.exists():
            if op.path_after.is_dir():
                op.path_after.rmdir()
            else:
                op.path_after.unlink()
        # TODO: what to do if path_after doesn't exist?

    def backup_dir(self) -> AbsolutePath:
        return self.directory / "backup"

    @classmethod
    def _choose_directory(cls) -> AbsolutePath:
        # TODO: check permissions
        env_batch_dir = os.environ.get("BATCHOP_DIR")
        if env_batch_dir is not None:
            return AbsolutePath(Path(env_batch_dir).absolute())

        env_xdg_data_home = os.environ.get("XDG_DATA_HOME")
        if env_xdg_data_home is not None:
            return AbsolutePath(Path(env_xdg_data_home).absolute() / "batchop")

        local_share = Path.home() / ".local" / "share"
        if local_share.exists() and local_share.is_dir():
            return AbsolutePath(local_share / "batchop")

        return AbsolutePath(Path.home().absolute() / ".batchop")


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


def _detect_name_collisions(paths_renamed: Dict[AbsolutePath, str]) -> None:
    # new path --> old path
    already_seen: Dict[Path, Path] = {}
    for old_path, new_name in paths_renamed.items():
        new_path = old_path.parent / new_name
        if new_path in already_seen:
            raise exceptions.PathCollision(path1=old_path, path2=already_seen[new_path])

        already_seen[new_path] = old_path


def _detect_duplicates(fileset: FileSet) -> None:
    already_seen: Dict[str, Path] = {}
    for path in fileset:
        other = already_seen.get(path.name)
        if other is not None:
            raise exceptions.PathCollision(path1=path, path2=other)
        already_seen[path.name] = path


def _sort_undo_ops(ops: List[InvocationOp]) -> None:
    def _key(op: InvocationOp) -> int:
        if op.op_type == OP_TYPE_CREATE:
            return 2
        else:
            return 1

    ops.sort(key=_key)
