// Compile-time compression of the person-names corpus.
//
// `rust/data/names/person_names.txt` is committed as plain UTF-8 (~8.5 MB)
// so git diffs stay inspectable when the corpus regenerates. At build
// time this script zstd-compresses the file (~2.7 MB) to `OUT_DIR`,
// and the Rust code in `names::person_names` picks it up via
// `include_bytes!(concat!(env!("OUT_DIR"), "/person_names.txt.zst"))`.
// Runtime decodes once on first access.
//
// If the source file is missing (e.g. a fresh checkout before
// `contrib/namesdb/Makefile::dump` has been run, or when the namesdb
// pipeline is deliberately skipped), we emit an empty blob and print
// a cargo warning. Callers of `names::person_names::raw()` will see the
// empty string — the future tagger treats this as "no person corpus
// available, produce no NAME_QID symbols."

use std::env;
use std::fs;
use std::path::PathBuf;

fn main() {
    let out_dir = PathBuf::from(env::var("OUT_DIR").expect("OUT_DIR set by cargo"));
    let source_path = PathBuf::from("data/names/person_names.txt");
    let dest_path = out_dir.join("person_names.txt.zst");

    println!("cargo:rerun-if-changed=data/names/person_names.txt");
    println!("cargo:rerun-if-changed=build.rs");

    let Ok(bytes) = fs::read(&source_path) else {
        println!(
            "cargo:warning=rust/data/names/person_names.txt not found — \
             compiling empty person-names corpus. Run `make -C contrib/namesdb dump` \
             to regenerate."
        );
        fs::write(&dest_path, [] as [u8; 0]).expect("write empty placeholder");
        return;
    };

    // Level 19 is the high-ratio tier — cold compression, but this
    // runs at build time only and gives the best wheel size. ~1 s for
    // the full corpus; not a build-time hot spot.
    let compressed =
        zstd::encode_all(bytes.as_slice(), 19).expect("zstd compress person_names.txt");
    fs::write(&dest_path, &compressed).expect("write compressed person_names.txt.zst");
}
