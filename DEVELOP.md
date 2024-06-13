*This information is for owners of the `batchop` package, not users.*

Run tests:

```python
$ poetry run pytest
```

Publish to PyPI:

1. Update version number in `pyproject.toml`.
2. Run `poetry build`.
3. Run `poetry publish`.

## Prior art
- [mmv](https://manpages.ubuntu.com/manpages/noble/en/man1/mmv.1.html) inspired the syntax for
  renaming.
- [rename](http://plasmasturm.org/code/rename/) is another utility for renaming files with patterns.
- [zfind](https://github.com/laktak/zfind) and [fselect](https://github.com/jhspetersson/fselect)
  similarly use a human-readable syntax to find files.
