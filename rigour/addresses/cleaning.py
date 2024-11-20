def clean_address(full: str) -> str:
    # TODO: there's probably a higher-performance way of doing this via
    # a regex or something.
    prev = None
    while prev != full:
        prev = full
        full = full.replace(" ,", ",")
        full = full.replace(",,", ",")
        full = full.replace("  ", " ")
        full = full.strip(",")
        full = full.strip()
    return full
