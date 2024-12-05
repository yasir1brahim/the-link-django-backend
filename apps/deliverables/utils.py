ANCHOR_REPR_DELIMITER = '$$$'


def format_anchor_repr(anchor: list) -> str:
    # TODO: Is this good enough? Will this clash with any established practice?
    return ANCHOR_REPR_DELIMITER.join(anchor)
