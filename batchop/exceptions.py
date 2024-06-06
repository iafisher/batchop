class BatchOpError(Exception):
    pass


class BatchOpSyntaxError(BatchOpError):
    pass


class BatchOpImpossibleError(BatchOpError):
    pass
