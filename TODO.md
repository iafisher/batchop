## Bugs

- need to handle PermissionError gracefully -- how?
- "10 mb" doesn't parse, have to write it as one word: "10mb"

## Features

- `undo` command
    - undo all
    - undo list and undo <n>
        - undo move, undo delete, etc.
        - tricky because undoing old old commands may not work
    - does stacked undo work?
    - detect changes in directory and require confirmation if so
- `replace` command
    - `replace "foo" with "bar" in <fileset>`
- shortcut for single replacement: `rename "*.md" to "*.mdx"` instead of `rename "*.md" to "#1.mdx"`
- `run` command
    - `run cat on <fileset>`
- `count lines` command
- `gc`/`cleanup` command
- `.gitignore` support
    - (if current directory has .git, apply .gitignore)
    - probably also ignore hidden files by default
    - tricky when you have multiple gitignores in the same repository
    - <https://github.com/mherrmann/gitignore_parser>
- support glob patterns for `is in` filter
- support regex patterns for `is in` filter
- do symlinks work?
- `--verbose` flag
- simple optimizer for filter order
    - drop `FilterTrue`
    - put most restrictive filters first
    - remove duplicates
- handle non-UTF8 file names
- transactional semantics – roll back operations that have already been completed?
- `.batchop/backup` should have a directory per invocation, and maybe use original file names unless there would be a
  collision?
- `delete a/b exclude a/b/c` should be rejected as we can't delete `a/b` without also deleting `a/b/c`
- could optimize `.stat()` usage, calling it multiple times on the same path
- custom help text

## More filters

- `X or Y` filter
- filter on owner: `is owned by X`
- filter on time modified (needs design)
- filter on permissions: `is executable`

## Cleanup/testing

- inject synthetic errors to test error handling in middle of operation
- get rid of `cwd` parameters in parser

## Questions

- Should `list '*.md'` match all Markdown files or only the ones at the top level?
- How should `> 10 mb` handle directories?
    - Option 1: directories filtered out
    - Option 2: directories passed through
    - Option 3: filter directories whose total size is greater than 10 megabytes
- Should it ever be possible to mix files and folders in the same command?
- Should `not in __pycache__` means "not in `__pycache__` in the root directory", or
  "not in any directory named `__pycache__`"?
    - For `__pycache__` the latter interpretation seems more intuitive, but if the directory is
      some specific name like `batchop`, then the former.
    - Idea: if contains a slash, always interpreted as a path; otherwise interpreted as a name
- Should hidden files include `.a/b` or only `.b`?
    - i.e., is a file hidden if in a hidden directory, or only if itself hidden?
    - What if we are inside a hidden directory?

## Ideas

- Use `NewType` to define `AbsolutePath` and `UnknownPath`
    - consistent standard for how paths are represented internally; must work for both command-line and Python API
    - For filters: relative vs. absolute doesn't matter as long as the test paths and the filter-internal paths are
      consistent
    - For output: should be relative
    - For undo: *must* be absolute
    - Command-line tool can assume that root == cwd, but Python API can't
- Distinction between lazy and concrete filesets
    - lazy is defined by a set of filters and can be recalculated/modified
    - concrete is a concrete list of files
    - once lazy is resolved, it turns into concrete and no longer need to recalculate filters/size
    - this could have weird interactions with recurse behavior... or maybe not
- Imperative commands (`move`, `rename`, `delete`) have normal Unix syntax
    - batchop remembers last `list` command and saves fileset as special value `_` which can be referenced in later
      commands, e.g. `bop list files gt 10 mb; bop delete _`
    - Drawbacks
        - Interference between batchop sessions in different terminals
        - Less convenient than being able to specify filters in-line
            - however avoids weird things like `bop delete '*.txt'` having different behavior than `bop delete *.txt`
    - Rename `list` to `find`? `query`? `q`?
- Decouple 'FilterSet' from 'FileSet'?
