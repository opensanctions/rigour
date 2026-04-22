import gc
import resource


def get_mem() -> int:
    gc.collect(2)
    gc.collect()
    gc.collect()
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss


def sizeof_fmt(num: float, suffix="B"):
    for unit in ("", "Ki", "Mi", "Gi", "Ti", "Pi", "Ei", "Zi"):
        if abs(num) < 1024.0:
            return f"{num:3.1f}{unit}{suffix}"
        num /= 1024.0
    return f"{num:.1f}Yi{suffix}"


def run_checks():
    print("Initial:", sizeof_fmt(get_mem()))
    from rigour.territories import lookup_territory

    lookup_territory("Germany")

    print("After loading territories:", sizeof_fmt(get_mem()))

    from rigour.addresses import normalize_address, remove_address_keywords

    addr = "123 Main St, Springfield, IL"
    addr = normalize_address(addr)
    if addr:
        remove_address_keywords(addr)

    print("After loading addresses:", sizeof_fmt(get_mem()))

    from rigour.names import remove_org_types

    org = "Example Limited Liability Company"
    org = remove_org_types(org)

    print("After loading org types:", sizeof_fmt(get_mem()))

    from rigour.names import NameTypeTag, analyze_names

    analyze_names(NameTypeTag.ORG, ["Example Organization"])

    print("After loading org names:", sizeof_fmt(get_mem()))

    analyze_names(NameTypeTag.PER, ["John Doe"])

    print("After loading person names:", sizeof_fmt(get_mem()))


if __name__ == "__main__":
    run_checks()
