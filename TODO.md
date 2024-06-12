- `rename` command (needs design)
- `trash` command
- `undo` command
- `move` command
    - `move <fileset> to <dest>`
- `replace` command
    - `replace "foo" with "bar" in <fileset>`
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
- how to handle special files?

## Questions
- Should `list '*.md'` match all Markdown files or only the ones at the top level?
- How should `> 10 mb` handle directories?
    - Option 1: directories filtered out
    - Option 2: directories passed through
    - Option 3: filter directories whose total size is greater than 10 megabytes
- Should it ever be possible to mix files and folders in the same command?