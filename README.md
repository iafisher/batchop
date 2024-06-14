**WARNING: `batchop` is in early beta. It has bugs. Only use it on files that you have backed up.**

`batchop` is a command-line tool and Python library for doing operations on sets of files, with an
intuitive, human-readable syntax.

```shell
# or use `pipx` to install it in an isolated environment
$ pip install batchop

$ alias bop=batchop
$ bop list files with ext jpg
05_27_beach.jpg
05_27_cabin.jpg
05_28_hike.jpg
```

`batchop` can **list**, **count**, **rename**, **move**, and **delete** files. It's a general-purpose
replacement for `find`, `xargs`, hand-written `bash` loops, etc.

```shell
# change mm/dd to dd/mm/yyyy
$ bop rename '*_*_*.jpg' to '#2_#1_2024_#3.jpg'

# delete big out-takes
$ bop delete '*.jpg' in outtakes gt 5mb
```

Oh, and you can **undo** commands, too:

```shell
$ bop undo
# out-takes are back!
```
