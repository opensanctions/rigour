import resource

from rigour.names import load_person_names_mapping


def get_mem() -> int:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss


def sizeof_fmt(num: float, suffix="B"):
    for unit in ("", "Ki", "Mi", "Gi", "Ti", "Pi", "Ei", "Zi"):
        if abs(num) < 1024.0:
            return f"{num:3.1f}{unit}{suffix}"
        num /= 1024.0
    return f"{num:.1f}Yi{suffix}"


def run_checks():
    print("Initial:", sizeof_fmt(get_mem()))
    mapping = load_person_names_mapping()
    assert len(mapping) > 0
    print("After loading names mapping:", sizeof_fmt(get_mem()))


if __name__ == "__main__":
    run_checks()
