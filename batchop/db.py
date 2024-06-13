import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import List, NewType, Optional, Tuple


# this must be incremented when schema changes
# TODO: automatically handle migration from old to new version
DATABASE_VERSION = 1


InvocationId = NewType("InvocationId", str)
OpType = NewType("OpType", str)

OP_TYPE_DELETE = OpType("delete")
OP_TYPE_RENAME = OpType("rename")

# maintain separate lists of invocations for different contexts
INVOCATION_CONTEXT_CLI = "cli"
INVOCATION_CONTEXT_PYTHON = "python"


@dataclass
class Invocation:
    invocation_id: InvocationId
    context: str
    cmdline: str
    # TODO: is undoable field needed, or just don't record invocations that are not undoable?
    undoable: bool
    time_invoked_ms: int


_INVOCATION_FIELDS = "invocation_id, context, cmdline, undoable, time_invoked_ms"


@dataclass
class InvocationOp:
    invocation_id: InvocationId
    op_type: OpType
    path_before: Path
    path_after: Path


_INVOCATION_OP_FIELDS = "invocation_id, op_type, path_before, path_after"


class Database:
    path: Path
    conn: sqlite3.Connection
    context: str

    def __init__(self, directory: Path, *, context: str) -> None:
        self.path = directory / self._make_name()
        self.context = context
        # https://iafisher.com/blog/2021/10/using-sqlite-effectively-in-python
        self.conn = sqlite3.Connection(self.path, isolation_level=None)
        self.conn.execute("PRAGMA foreign_keys = 1")

    def create_tables(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS invocation(
              invocation_id TEXT PRIMARY KEY,
              context TEXT NOT NULL,
              cmdline TEXT NOT NULL,
              undoable INTEGER NOT NULL,
              time_invoked_ms INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS invocation_op(
              invocation_id TEXT NOT NULL,
              op_type TEXT NOT NULL CHECK (op_type IN ('delete', 'rename')),
              path_before TEXT NOT NULL,
              path_after TEXT NOT NULL,

              FOREIGN KEY (invocation_id) REFERENCES invocation(invocation_id) ON DELETE CASCADE
            );
            """
        )

    def create_invocation(self, cmdline: str, *, undoable: bool) -> InvocationId:
        time_invoked_ms = int(time.time() * 1000)
        invocation_id = uuid.uuid4().hex
        cursor = self.conn.execute(
            f"""
            INSERT INTO invocation({_INVOCATION_FIELDS})
            VALUES (?, ?, ?, ?, ?)
            """,
            (invocation_id, self.context, cmdline, undoable, time_invoked_ms),
        )
        return InvocationId(invocation_id)

    def create_invocation_op(
        self,
        invocation_id: InvocationId,
        op_type: OpType,
        path_before: Path,
        path_after: Path,
    ) -> None:
        self.conn.execute(
            f"""
            INSERT INTO invocation_op({_INVOCATION_OP_FIELDS})
            VALUES (?, ?, ?, ?)
            """,
            (invocation_id, op_type, str(path_before), str(path_after)),
        )

    def get_last_invocation(self) -> Tuple[Optional[Invocation], List[InvocationOp]]:
        cursor = self.conn.execute(
            f"""
            SELECT {_INVOCATION_FIELDS}
            FROM invocation
            WHERE context = ?
            ORDER BY time_invoked_ms DESC
            LIMIT 1
            """,
            (self.context,),
        )
        row = cursor.fetchone()
        if row is None:
            return None, []

        invocation = Invocation(
            InvocationId(row[0]), row[1], row[2], bool(row[3]), row[4]
        )

        cursor = self.conn.execute(
            f"""
            SELECT {_INVOCATION_OP_FIELDS}
            FROM invocation_op
            WHERE invocation_id = ?
            """,
            (invocation.invocation_id,),
        )
        rows = cursor.fetchall()
        ops = [
            InvocationOp(
                InvocationId(row[0]), OpType(row[1]), Path(row[2]), Path(row[3])
            )
            for row in rows
        ]
        return invocation, ops

    def delete_invocation(self, invocation_id: InvocationId) -> None:
        self.conn.execute(
            """
            DELETE FROM invocation
            WHERE invocation_id = ?
            """,
            (invocation_id,),
        )

    @classmethod
    def _make_name(cls) -> str:
        return f"db_{DATABASE_VERSION}.sqlite3"
