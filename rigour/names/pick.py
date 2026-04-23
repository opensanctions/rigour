from typing import Dict, List, Optional

from rigour._core import pick_name as pick_name
from rigour._core import reduce_names as reduce_names
from rigour.langs import LangStr, PREFERRED_LANG, PREFERRED_LANGS
from rigour.text import levenshtein


def pick_lang_name(names: List[LangStr]) -> Optional[str]:
    """Pick the best name from a list of LangStr objects, prioritizing the preferred language.

    Args:
        names (List[LangStr]): A list of LangStr objects with language information.

    Returns:
        Optional[str]: The best name for display.
    """
    if len(names) == 0:
        return None
    preferred = [str(n) for n in names if n.lang == PREFERRED_LANG]
    if len(preferred) > 0:
        picked = pick_name(preferred)
        if picked is not None:
            return picked
    preferred = [str(n) for n in names if n.lang in PREFERRED_LANGS]
    if len(preferred) > 0:
        picked = pick_name(preferred)
        if picked is not None:
            return picked
    return pick_name([str(n) for n in names])


def representative_names(
    names: List[str],
    limit: int,
    cluster_threshold: float = 0.3,
) -> List[str]:
    """Pick display representatives of the distinct name-clusters in a bag
    of aliases.

    Useful when a downstream process (e.g. building a search query) wants to
    probe the alias space broadly with a small number of queries. For a
    person with 20 transliterations of one name, this returns 1
    representative; for a person with two genuinely different names (e.g.
    Nelson Mandela / Rolihlahla Mandela), it returns 2 — because N
    transliterations of the same name don't add recall, but a second
    *name* does.

    `limit` is a cap, not a quota: if all aliases collapse into one
    cluster, the result is one name regardless of `limit`. Returned
    strings are originals from the input (via :func:`pick_name` per
    cluster), ordered by centroid first, then farthest cluster, etc.

    Args:
        names: input aliases, typically all belonging to one entity.
        limit: upper bound on output size.
        cluster_threshold: normalized Levenshtein distance (0..1) above
            which two names are considered distinct *names* rather than
            variants of one. Default 0.3 keeps transliterations together
            while separating genuinely different names.
    """
    if limit <= 0 or not names:
        return []
    reduced = reduce_names(names)
    if len(reduced) <= 1:
        return list(reduced)

    # Casefolded/whitespace-normalised form of each reduced name, for
    # distance measurement. The originals are what we return.
    normed: Dict[str, str] = {}
    for n in reduced:
        nn = " ".join(n.casefold().split())
        if nn:
            normed[n] = nn

    centroid = pick_name(reduced)
    if centroid is None or centroid not in normed:
        return []

    def _dist(a: str, b: str) -> float:
        return levenshtein(a, b) / max(len(a), len(b), 1)

    # Farthest-point-first seed selection with threshold stopping: each
    # new seed must be more than `cluster_threshold` away from every
    # already-picked seed, else we've run out of distinct clusters.
    seeds: List[str] = [centroid]
    while len(seeds) < limit:
        outlier: Optional[str] = None
        outlier_d = 0.0
        for n in reduced:
            if n in seeds or n not in normed:
                continue
            nn = normed[n]
            min_d = min(_dist(nn, normed[s]) for s in seeds)
            if min_d > outlier_d:
                outlier_d = min_d
                outlier = n
        if outlier is None or outlier_d <= cluster_threshold:
            break
        seeds.append(outlier)

    if len(seeds) == 1:
        return seeds

    # Assign each reduced name to its nearest seed, then pick_name per
    # cluster so the returned rep is the best display form of its group
    # rather than whichever outlier happened to be picked as the seed.
    clusters: List[List[str]] = [[s] for s in seeds]
    for n in reduced:
        if n in seeds or n not in normed:
            continue
        nn = normed[n]
        best_i = 0
        best_d = float("inf")
        for i, s in enumerate(seeds):
            d = _dist(nn, normed[s])
            if d < best_d:
                best_d = d
                best_i = i
        clusters[best_i].append(n)

    reps: List[str] = []
    for cluster in clusters:
        rep = pick_name(cluster)
        if rep is not None:
            reps.append(rep)
    return reps


def pick_case(names: List[str]) -> str:
    """Pick the best mix of lower- and uppercase characters from a set of names
    that are identical except for case. If the names are not identical, undefined
    things happen (not recommended).

    Rust-backed via :func:`rigour._core.pick_case`. The Rust
    implementation returns `None` for empty input; this Python wrapper
    raises `ValueError` to preserve the pre-port contract that
    external callers rely on.

    Args:
        names (List[str]): A list of identical names in different cases.

    Returns:
        str: The best name for display.
    """
    from rigour._core import pick_case as _pick_case

    result = _pick_case(names)
    if result is None:
        raise ValueError("Cannot pick a name from an empty list.")
    return result
