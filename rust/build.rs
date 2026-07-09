// Compile-time zstd compression for data files embedded in the
// binary. Source files are committed plain (JSON indented, text raw
// UTF-8) for diffability; `build.rs` compresses each into `OUT_DIR`
// and the corresponding Rust module picks it up via `include_bytes!`.
//
// Current files:
//   - `data/names/person_names.txt`        (~8.1 MB → ~2.7 MB)
//   - `data/names/symbols.json`            (~85 KiB → ~12 KiB)
//   - `data/names/org_types.json`          (~125 KiB → ~15 KiB)
//   - `data/territories/data.jsonl`        (~783 KiB → ~214 KiB)
//
// All source files are committed, so a missing one means a broken
// checkout — fail the build rather than embed an empty blob that
// would ship as a silently non-functional wheel (empty tagger, zero
// territories).

use std::env;
use std::fs;
use std::path::PathBuf;

struct Compress {
    src: &'static str,     // path under rust/
    dst: &'static str,     // filename under OUT_DIR
    missing: &'static str, // error detail if source file is absent
}

const FILES: &[Compress] = &[
    Compress {
        src: "data/names/person_names.txt",
        dst: "person_names.txt.zst",
        missing: "rust/data/names/person_names.txt not found. Run \
                  `make -C contrib/namesdb dump` to regenerate.",
    },
    Compress {
        src: "data/territories/data.jsonl",
        dst: "territories.jsonl.zst",
        missing: "rust/data/territories/data.jsonl not found. Run \
                  `make build-territories` to regenerate.",
    },
    Compress {
        src: "data/names/symbols.json",
        dst: "symbols.json.zst",
        missing: "rust/data/names/symbols.json not found. Run \
                  `make build-names` to regenerate.",
    },
    Compress {
        src: "data/names/org_types.json",
        dst: "org_types.json.zst",
        missing: "rust/data/names/org_types.json not found. Run \
                  `make build-names` to regenerate.",
    },
];

fn main() {
    let out_dir = PathBuf::from(env::var("OUT_DIR").expect("OUT_DIR set by cargo"));
    println!("cargo:rerun-if-changed=build.rs");

    for entry in FILES {
        let source_path = PathBuf::from(entry.src);
        let dest_path = out_dir.join(entry.dst);
        println!("cargo:rerun-if-changed={}", entry.src);

        let bytes = fs::read(&source_path).unwrap_or_else(|_| panic!("{}", entry.missing));

        // Level 19 is the high-ratio tier — slow compression, but this
        // runs at build time only and gives the best wheel size.
        let compressed = zstd::encode_all(bytes.as_slice(), 19).expect("zstd compress source file");
        fs::write(&dest_path, &compressed).expect("write compressed artifact");
    }
}
