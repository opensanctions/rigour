// Address analysis for the comparison pipeline — tokenize and
// classify address strings into `Address { tokens, scripts }`.
// Rust-internal for now: the PyO3 comparison surface lands with
// the scorer.

pub mod analyze;
pub mod tagger;
pub mod token;
