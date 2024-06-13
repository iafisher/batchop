from .common import BatchOpError, plural


def confirm_delete_n_files(nfiles: int, ndirs: int, nbytes: int) -> str:
    s1 = plural(nfiles, "file", color=True)
    s2 = plural(ndirs, "directory", "directories", color=True)
    # TODO: human-readable size units
    s3 = plural(nbytes, "byte", color=True)

    if nfiles > 0:
        if ndirs > 0:
            return f"Delete {s1} and {s2} totaling {s3}? "
        else:
            return f"Delete {s1} totaling {s3}? "
    else:
        if ndirs > 0:
            return f"Delete {s2} totaling {s3}? "
        else:
            raise ValueError


def confirm_rename_n_files(nfiles: int) -> str:
    # TODO: give more information
    s1 = plural(nfiles, "file", color=True)
    return f"Rename {s1}? "
