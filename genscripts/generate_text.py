from typing import Any

import yaml

from genscripts.util import (
    RESOURCES_PATH,
    RUST_DATA_PATH,
    norm_string,
    write_json,
)


def _sorted_unique_norm(values: list[str]) -> list[str]:
    """Normalise, dedupe, and sort a flat string list — stable JSON out."""
    return sorted({norm_string(v) for v in values if norm_string(v)})


def generate_ordinals() -> None:
    """Emit `rust/data/text/ordinals.json` — array of `{number, forms}`
    records, sorted by number. Consumed by the Rust-side
    `ordinals_dict()` accessor (Python consumers) and by the Rust
    tagger build path."""
    ordinals_path = RESOURCES_PATH / "text" / "ordinals.yml"
    with open(ordinals_path, "r", encoding="utf-8") as ufh:
        ordinals_mapping: dict[str, dict[int, list[str]]] = yaml.safe_load(ufh.read())

    records: list[dict[str, Any]] = []
    for number, forms in sorted(ordinals_mapping["ordinals"].items()):
        assert number is not None
        sorted_forms = _sorted_unique_norm(forms)
        records.append({"number": number, "forms": sorted_forms})

    out_path = RUST_DATA_PATH / "text" / "ordinals.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(out_path, records, indent=True)


def generate_stopwords() -> None:
    """Emit `rust/data/text/stopwords.json` — a three-field object
    (`stopwords`, `nullwords`, `nullplaces`) of sorted de-duplicated
    normalised string lists. Consumed by the Rust-side `stopwords_list`
    / `nullwords_list` / `nullplaces_list` accessors."""
    stopwords_path = RESOURCES_PATH / "text" / "stopwords.yml"
    with open(stopwords_path, "r", encoding="utf-8") as ufh:
        stopword_lists: dict[str, list[str]] = yaml.safe_load(ufh.read())

    out_data: dict[str, list[str]] = {}
    for key, value in stopword_lists.items():
        # YAML section names arrive as UPPERCASE_WORDS. Lower-case them
        # for the JSON field names — the Rust side spells them
        # `stopwords`/`nullwords`/`nullplaces` in `serde(rename_all)`-
        # friendly snake_case.
        out_data[key.strip().lower()] = _sorted_unique_norm(value)

    out_path = RUST_DATA_PATH / "text" / "stopwords.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(out_path, out_data, indent=True)


if __name__ == "__main__":
    generate_ordinals()
    generate_stopwords()
