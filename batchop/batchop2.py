import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from . import confirmation, english, exceptions
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
from .fileset2 import FilterSet3


@dataclass
class DeleteResult:
    paths_deleted: List[AbsolutePath]


@dataclass
class UndoResult:
    original_cmdline: str
    num_ops: int


class BatchOp2:
    # this is the directory the user is querying
    root: AbsolutePath
    # this is BatchOp's bookkeeping directory
    directory: Path
    db: Database

    _BACKUP_DIR = "backup"

    def __init__(
        self, root: Optional[PathLike] = None, context: str = INVOCATION_CONTEXT_PYTHON
    ) -> None:
        if root is None:
            self.root = abspath(Path.cwd())
        else:
            self.root = abspath(root)

        self.directory = self._ensure_directory()
        self.db = Database(self.directory, context=context)
        self.db.create_tables()

    def delete(
        self,
        filterset: FilterSet3,
        *,
        require_confirm: bool = True,
        dry_run: bool = False,
        original_cmdline: str = "",
    ) -> Optional[DeleteResult]:
        fileset = filterset.resolve(self.root, recursive=True)
        if fileset.is_empty():
            raise exceptions.EmptyFileSet

        if require_confirm:
            if not confirmation.confirm_operation_on_fileset2(fileset, "Delete"):
                return None

        paths_deleted = []
        undo_mgr = UndoManager.start(
            self.db, self.directory / self._BACKUP_DIR, original_cmdline
        )
        for p in fileset.exclude_children():
            if not dry_run:
                new_path = undo_mgr.add_op(OP_TYPE_DELETE, p)
                shutil.move(p, new_path)

            paths_deleted.append(p)

        return DeleteResult(paths_deleted)

    def count(self, filterset: FilterSet3) -> int:
        fileset = filterset.resolve(self.root, recursive=False)
        return len(fileset)

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
            # TODO: cross-platform
            shutil.move(op.path_after, op.path_before)

    def _undo_create(self, op: InvocationOp) -> None:
        if op.path_after.exists():
            if op.path_after.is_dir():
                op.path_after.rmdir()
            else:
                op.path_after.unlink()
        # TODO: what to do if path_after doesn't exist?

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
