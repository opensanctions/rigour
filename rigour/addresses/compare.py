"""Compare postal address strings for referring to the same place."""

from rigour._core import AddressMatch
from rigour._core import address_fingerprint as _address_fingerprint
from rigour._core import compare_address as _compare_address
from rigour._core import compare_address_many as _compare_address_many
from rigour._core import match_addresses as _match_addresses

__all__ = [
    "AddressMatch",
    "address_fingerprint",
    "compare_address",
    "compare_address_many",
    "match_addresses",
]


def compare_address(query: str, result: str) -> float:
    """Compare two address strings, scoring how likely they denote
    the same place.

    Both strings are analyzed into classed tokens (numbers, keyword
    signifiers like `str.`/`ул.`, territory names, free text) and
    greedily aligned: numbers must match exactly, keywords match
    across alias forms (`boulevard`/`blvd`), territory names match
    across languages via their code (`Syria`/`Сирия`), and free text
    matches by edit distance over transliterated forms. The score is
    the length-weighted share of aligned tokens, and a pair of
    numbers where each side asserts a value the other lacks (a
    differing house or unit number) is penalized far beyond its
    length. Comparison is order-independent, so differently arranged
    address parts do not lower the score.

    Score semantics, measured on the labelled benchmark corpus in
    `contrib/address_bench`: equivalent renderings of one address
    score 1.0; transliterated or partly translated matches typically
    land between 0.5 and 0.9; an address and its less specific
    prefix (street dropped, city kept) around 0.6; pairs with
    conflicting house or unit numbers are pushed toward 0.0. The
    accuracy-optimal decision threshold on that corpus is ~0.3 —
    substantially lower than typical name-similarity calibrations.

    Analysis results are memoized in a process-wide cache, so
    comparing one address against many candidates re-analyzes the
    repeated side only once. The GIL is released while comparing.

    Args:
        query: An address, as one full string.
        result: The address to compare against, as one full string.

    Returns:
        A similarity score between 0.0 and 1.0. Empty or
        punctuation-only input scores 0.0 against everything.
    """
    return _compare_address(query, result)


def compare_address_many(queries: list[str], results: list[str]) -> float:
    """Compare two sets of address strings and return the best
    pairwise score.

    The score-only form of
    [match_addresses][rigour.addresses.compare.match_addresses]:
    same pairing, same analysis cache, without the match object.

    Args:
        queries: Addresses of one entity, each as one full string.
        results: Addresses of the other entity, each as one full
            string.

    Returns:
        The highest pairwise similarity score between 0.0 and 1.0;
        0.0 when either list is empty or nothing is comparable.
    """
    return _compare_address_many(queries, results)


def match_addresses(queries: list[str], results: list[str]) -> AddressMatch | None:
    """Compare two sets of address strings and return the best
    pairwise match with the evidence behind it.

    Scores every query against every result with
    [compare_address][rigour.addresses.compare.compare_address] and
    returns the winning pair as an
    [AddressMatch][rigour._core.AddressMatch]: its `score`, the two
    input strings that produced it (`query`, `result`), and a
    one-line `detail` describing how the tokens aligned. Each
    distinct string is analyzed only once, so the list×list loop is
    substantially cheaper than the equivalent pairwise calls.

    The `detail` line lists analyzed tokens (lowercased, narrowly
    transliterated) separated by spaces: aligned tokens first, in
    query order, then the leftovers of each side.

    | form | meaning |
    |---|---|
    | `berlin` | aligned, identical on both sides |
    | `boulevard~blvd` | aligned by edit distance, keyword alias or territory code (query left, result right) |
    | `-10115` | only in the query address |
    | `+la` | only in the result address |

    A line without `~`, `-` or `+` is an exact match; leftovers on
    one side only mark a subset relation; a `-5 +7` pair of numbers
    is the penalized house- or unit-number conflict.

    Args:
        queries: Addresses of one entity, each as one full string.
        results: Addresses of the other entity, each as one full
            string.

    Returns:
        The best-scoring pair, or `None` when either list is empty or
        contains nothing analyzable (only punctuation). A pair with
        nothing in common is still returned, with a score of 0.0.
    """
    return _match_addresses(queries, results)


def address_fingerprint(text: str) -> str | None:
    """Serialize an address string into a deterministic key for
    deduplication and graph node identity.

    The address is analyzed into classed tokens and each token is
    reduced to its most canonical form: numbers become plain digit
    strings (`№17`, `17.` and `１７` all key as `17`), address
    keywords become their canonical short form (`Boulevard` and
    `blvd.` both key as `blvd`), unambiguous territory names in any
    supported language become their territory code (`Syria`, `Syrian
    Arab Republic` and `Сирия` all key as `sy`), and free text is
    transliterated where a narrow, systematic romanization exists.
    Token order is preserved: addresses that differ only by
    transposed numbers (`д. 17 стр. 1` versus `д. 1 стр. 17`) must
    not key identically, so differently ordered renderings of one
    address also produce different keys — collapsing those is left
    to fuzzier machinery. Use this function to key or deduplicate address
    records; to score how similar two addresses are, use
    [compare_address][rigour.addresses.compare.compare_address],
    which shares the same analysis (and its cache) but aligns tokens
    order-independently and fuzzily.

    The output is lowercase, space-separated, and ASCII except for
    free-text tokens in scripts without a systematic romanization
    (Chinese, Arabic, ...), which pass through in their native
    script. Callers that require pure-ASCII identifiers should
    slug-encode the result (e.g. `normality.slugify`). Fingerprints
    are stable within one version of rigour but may change between
    versions as the underlying resources grow; do not persist them
    across upgrades without re-keying.

    Args:
        text: An address, as one full string.

    Returns:
        The fingerprint string, or `None` when the input is empty or
        contains nothing analyzable (only punctuation).
    """
    return _address_fingerprint(text)
