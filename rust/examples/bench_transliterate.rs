// Pure-Rust microbenchmark for ascii_text / latinize_text. No Python in the
// loop — isolates the library (ICU4X + our wrapper) cost from the PyO3 FFI
// overhead that bench_transliteration.py also measures.
//
// Run: `cargo run --release --example bench_transliterate --manifest-path rust/Cargo.toml`

use std::hint::black_box;
use std::time::Instant;

use rigour_core::text::transliterate::{ascii_text, latinize_text};

const CORPUS: &[(&str, &str)] = &[
    ("ascii", "John Spencer"),
    ("latin_diacritics", "François Müller"),
    ("cyrillic_short", "Владимир Путин"),
    ("cyrillic_long", "Владимир Владимирович Путин"),
    ("chinese", "招商银行有限公司"),
    ("greek", "Κυριάκος Μητσοτάκης"),
    ("arabic", "محمد بن سلمان آل سعود"),
    ("armenian", "Միթչել Մակքոնել"),
    ("georgian", "მიხეილ სააკაშვილი"),
    ("korean", "김민석 박근혜"),
    ("japanese", "ウラジーミル・プーチン"),
    ("mixed_two", "Hello мир"),
    ("mixed_three", "Hello мир 中国"),
];

const ITERS: usize = 1000;

fn fmt_ns(ns: f64) -> String {
    if ns < 1_000.0 {
        format!("{:.0} ns", ns)
    } else if ns < 1_000_000.0 {
        format!("{:.2} µs", ns / 1_000.0)
    } else {
        format!("{:.2} ms", ns / 1_000_000.0)
    }
}

fn bench(name: &str, inputs: &[String], f: impl Fn(&str) -> String) -> f64 {
    // warmup: one call to trigger lazy thread-local init for the relevant script
    let _ = f(&inputs[0]);
    let start = Instant::now();
    for s in inputs {
        black_box(f(s));
    }
    let elapsed = start.elapsed();
    let per_call = elapsed.as_nanos() as f64 / ITERS as f64;
    println!("  {:<20} {}", name, fmt_ns(per_call));
    per_call
}

fn main() {
    println!("== ascii_text (pure Rust, no PyO3) ==");
    for (label, base) in CORPUS {
        let inputs: Vec<String> = (0..ITERS).map(|i| format!("{} {}", base, i)).collect();
        bench(label, &inputs, ascii_text);
    }
    println!();
    println!("== latinize_text (pure Rust, no PyO3) ==");
    for (label, base) in CORPUS {
        let inputs: Vec<String> = (0..ITERS).map(|i| format!("{} {}", base, i)).collect();
        bench(label, &inputs, latinize_text);
    }
}
