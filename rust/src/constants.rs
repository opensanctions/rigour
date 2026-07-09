// Shared sizing constants for in-process memoization caches.
// Order-of-magnitude tiers, not individually tuned — new caches
// should pick a tier here rather than inventing their own size, so
// memo footprints stay comparable across the crate.

pub const MEMO_LARGE: usize = 200_000;
