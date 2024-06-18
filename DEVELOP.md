*This information is for owners of the `batchop` package, not users.*

Run tests:

```shell
$ poetry run pytest
```

Publish to PyPI:

1. Update version number in `pyproject.toml` and `batchop/__init__.py`.
2. Make a commit and push it to GitHub.
3. Run `poetry build`.
4. Run `poetry publish`.
5. Create a release on GitHub.
