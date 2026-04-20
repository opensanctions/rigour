// Shared sizing constants for in-process memoization caches.
// Mirrors `rigour/util.py:7-10` so Python and Rust callers agree on
// what "large" means when sizing an LRU. Order-of-magnitude buckets,
// not tuned individually; if a specific cache needs something else,
// pass a literal rather than inventing a new named tier.

pub const MEMO_TINY: usize = 128;
pub const MEMO_SMALL: usize = 2_000;
pub const MEMO_MEDIUM: usize = 20_000;
pub const MEMO_LARGE: usize = 1 << 17; // 131_072
