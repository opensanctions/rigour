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
// If a source file is missing (fresh checkout before
// `contrib/namesdb/Makefile::dump` has been run, for example), we emit
// an empty blob and print a cargo warning. Callers of the corresponding
// `raw()` loader see an empty string.

use std::env;
use std::fs;
use std::path::PathBuf;

struct Compress {
    src: &'static str,     // path under rust/
    dst: &'static str,     // filename under OUT_DIR
    missing: &'static str, // cargo warning if source file is absent
}

const FILES: &[Compress] = &[
    Compress {
        src: "data/names/person_names.txt",
        dst: "person_names.txt.zst",
        missing: "rust/data/names/person_names.txt not found — \
                  compiling empty person-names corpus. Run \
                  `make -C contrib/namesdb dump` to regenerate.",
    },
    Compress {
        src: "data/territories/data.jsonl",
        dst: "territories.jsonl.zst",
        missing: "rust/data/territories/data.jsonl not found — \
                  compiling empty territories blob. Run \
                  `make build-territories` to regenerate.",
    },
    Compress {
        src: "data/names/symbols.json",
        dst: "symbols.json.zst",
        missing: "rust/data/names/symbols.json not found — \
                  compiling empty symbols blob. Run \
                  `make build-names` to regenerate.",
    },
    Compress {
        src: "data/names/org_types.json",
        dst: "org_types.json.zst",
        missing: "rust/data/names/org_types.json not found — \
                  compiling empty org-types blob. Run \
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

        let Ok(bytes) = fs::read(&source_path) else {
            println!("cargo:warning={}", entry.missing);
            fs::write(&dest_path, [] as [u8; 0]).expect("write empty placeholder");
            continue;
        };

        // Level 19 is the high-ratio tier — slow compression, but this
        // runs at build time only and gives the best wheel size.
        let compressed = zstd::encode_all(bytes.as_slice(), 19).expect("zstd compress source file");
        fs::write(&dest_path, &compressed).expect("write compressed artifact");
    }
}
