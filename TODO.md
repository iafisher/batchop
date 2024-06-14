## Bugs
- ~~preview file/directory count for e.g. `delete .venv` doesn't work~~
- don't exit interactive mode on parse error

## Features
- ~~`rename` command (needs design)~~
- ~~`trash` command~~
- `undo` command
    - ~~undo for delete~~
    - ~~undo for rename~~
    - undo all
    - undo list and undo <n>
        - undo move, undo delete, etc.
        - tricky because undoing old old commands may not work
    - does stacked undo work?
    - detect changes in directory and require confirmation if so
- `move` command
    - `move <fileset> to <dest>`
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
- ~~adjectives (`list all hidden files`)~~
- ~~pattern as a noun (`delete '*.md'`)~~
- ~~"directory" as synonym for "folder"~~
- support glob patterns for `is in` filter
- support regex patterns for `is in` filter
- do symlinks work?
- ~~how to handle special files?~~
- ~~shell quoting doesn't work, e.g. `rename '* *.md'` is passed as `['rename', '* *.md']` which becomes `'rename * *.md'` which can no longer be tokenized properly~~
    - if one command-line arg, tokenize it
    - if more than one, treat it as already tokenized?
        - might need a "subtokenize" routine, e.g. to split "10mb" into "10", "mb"
- `--verbose` flag
- simple optimizer for filter order
    - drop `FilterTrue`
    - put most restrictive filters first
    - remove duplicates
    - if `is in` filter then set that to the root
- handle non-UTF8 file names
- respect `NO_COLOR`
- transactional semantics – roll back operations that have already been completed?
- `.batchop/backup` should have a directory per invocation, and maybe use original file names unless there would be a
  collision?

## More filters
- `X or Y` filter
- filter on owner: `is owned by X`
- filter on time modified (needs design)
- filter on permissions: `is executable`

## Cleanup/testing
- just chdir to handle `-d` flag?
- inject synthetic errors to test error handling in middle of operation
- get rid of `cwd` parameters in parser
- put test resources directory on filesystem, copy before each test, and insert an empty directory in a known location

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
