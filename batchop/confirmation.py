import random
import sys

from . import english, exceptions
from .fileset import FileSet, RecurseBehavior


def confirm_operation_on_fileset(fs: FileSet, verb: str) -> bool:
    size = fs.calculate_size(recurse=RecurseBehavior.INCLUDE_DIR_CHILDREN)
    if size.is_empty():
        raise exceptions.EmptyFileSet

    while True:
        prompt = english.confirm_n_files_generic(verb, size)

        try:
            response = input(prompt).strip().lower()
        except EOFError:
            return False
        except KeyboardInterrupt:
            print()
            sys.exit(1)

        if response == "yes" or response == "y":
            return True
        elif response == "no" or response == "n":
            return False
        elif response == "help" or response == "h":
            # TODO: redefine command to interactively change fileset
            print("Available commands:")
            print("  yes:           confirm operation")
            print("  no:            decline operation")
            print("  list:          list files")
            print("  random:        list 10 random files")
            print("  help:          print this dialog")
        elif response in ("list", "l", "ls"):
            # TODO: inefficient to recalculate this
            for path in fs.resolve(recurse=RecurseBehavior.INCLUDE_DIR_CHILDREN):
                print(path)
        elif response == "random":
            # TODO: inefficient to recalculate this
            all_paths = list(fs.resolve(recurse=RecurseBehavior.INCLUDE_DIR_CHILDREN))
            random.shuffle(all_paths)
            for path in all_paths[:10]:
                print(path)
        else:
            print(
                "Response not understood. Please enter 'yes' or 'no', or 'help' to view available commands."
            )
