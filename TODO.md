- ~~`rename` command (needs design)~~
- `trash` command
- `undo` command
- `move` command
    - `move <fileset> to <dest>`
- `replace` command
    - `replace "foo" with "bar" in <fileset>`
- shortcut for single replacement: `rename "*.md" to "*.mdx"` instead of `rename "*.md" to "#1.mdx"`
- `run` command
    - `run cat on <fileset>`
- `count lines` command
- `.gitignore` support
    - (if current directory has .git, apply .gitignore)
    - probably also ignore hidden files by default
    - tricky when you have multiple gitignores in the same repository
    - <https://github.com/mherrmann/gitignore_parser>
- adjectives (`list all hidden files`)
- "directory" as synonym for "folder"
- support glob patterns for `is in` filter
- support regex patterns for `is in` filter
- do symlinks work?
- ~~how to handle special files?~~
- ~~shell quoting doesn't work, e.g. `rename '* *.md'` is passed as `['rename', '* *.md']` which becomes `'rename * *.md'` which can no longer be tokenized properly~~
    - if one command-line arg, tokenize it
    - if more than one, treat it as already tokenized?
        - might need a "subtokenize" routine, e.g. to split "10mb" into "10", "mb"

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
