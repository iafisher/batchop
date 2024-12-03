from pathlib import Path


class Base(Exception):
    # subclasses should override
    def fancy(self) -> str:
        return str(self)


class Syntax(Base):
    pass


class SyntaxEndOfInput(Syntax):
    def fancy(self) -> str:
        return "the command ended when more words were still expected"


class SyntaxExtraInput(Syntax):
    first_extra_token: str

    def __init__(self, first_extra_token: str) -> None:
        super().__init__()
        self.first_extra_token = first_extra_token

    def fancy(self) -> str:
        return f"there were unexpected extra words at the end of the command, starting with {self.first_extra_token!r}"


class SyntaxExpectedToken(Syntax):
    expected: str
    actual: str

    def __init__(self, *, expected: str, actual: str) -> None:
        super().__init__()
        self.expected = expected
        self.actual = actual

    def fancy(self) -> str:
        return f"the expected next word was {self.expected!r} but the actual word was {self.actual!r}"


class SyntaxNoMatchingPattern(Syntax):
    first_token: str

    def __init__(self, first_token: str) -> None:
        super().__init__()
        self.first_token = first_token

    def fancy(self) -> str:
        return f"could not understand the part of the command starting with {self.first_token!r}"


class SyntaxEmptyInput(Syntax):
    def fancy(self) -> str:
        return "the input is empty"


class SyntaxUnknownCommand(Syntax):
    command: str

    def __init__(self, command: str) -> None:
        super().__init__()
        self.command = command

    def fancy(self) -> str:
        return f"{self.command!r} is not a known command or verb"


class PathCollision(Base):
    path1: Path
    path2: Path

    def __init__(self, *, path1: Path, path2: Path) -> None:
        super().__init__()
        self.path1 = path1
        self.path2 = path2

    def fancy(self) -> str:
        return f"paths would collide:\n  {self.path1}\n  {self.path2}"


class UnknownSizeUnit(Base):
    unit: str

    def __init__(self, unit: str) -> None:
        super().__init__()
        self.unit = unit

    def fancy(self) -> str:
        return f"{self.unit!r} is not a known unit for file sizes"


class PathOutsideOfRoot(Base):
    path: Path
    root: Path

    def __init__(self, *, path: Path, root: Path) -> None:
        super().__init__()
        self.path = path
        self.root = root

    def fancy(self) -> str:
        return f"path is outside of root directory\n  path: {self.path}\n  root: {self.root}"


class EmptyFileSet(Base):
    def fancy(self) -> str:
        return "the file set is empty (are your filters too restrictive?)"


class FileNotFound(Base):
    path: Path

    def __init__(self, path: Path) -> None:
        super().__init__()
        self.path = path

    def fancy(self) -> str:
        return f"the file {self.path} does not exist"


class NotADirectory(Base):
    path: Path

    def __init__(self, path: Path) -> None:
        super().__init__()
        self.path = path

    def fancy(self) -> str:
        return f"{self.path} is not a directory"


# not a subclass of BatchOpError as it should not be caught
class Impossible(Exception):
    pass
