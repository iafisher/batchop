**WARNING: This project is not yet ready for public use.**

`batchop` is a command-line tool and Python library for doing operations on sets of files, with an
intuitive, human-readable syntax.

## Development
Run tests:

```python
$ poetry run pytest
```

Publish to PyPI:

```python
$ poetry build
$ poetry publish
```

## Prior art
- [zfind](https://github.com/laktak/zfind) and [fselect](https://github.com/jhspetersson/fselect)
  similarly use a human-readable syntax to find files.
