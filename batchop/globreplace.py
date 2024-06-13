import re


def glob_to_regex(globp: str) -> str:
    parts = globp.split("*")
    return "^" + "(.+?)".join(map(re.escape, parts)) + "$"


_glob_group_pattern = re.compile(r"#([0-9]+)")


def glob_to_regex_repl(globp: str) -> str:
    return _glob_group_pattern.sub(r"\\\1", globp)
