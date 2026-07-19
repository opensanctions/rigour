//! Shared input-size caps for the name-matching primitives.
//!
//! Corporate-registry and sanctions source data occasionally carries
//! paragraph-length "names" — concatenated aliases, or an address
//! pasted into a name field — and in an externally-fed matcher like
//! yente the inputs are caller-controllable. The name primitives run
//! super-linear DP / enumeration over their inputs, so each imposes
//! an explicit cap from here rather than trusting the data to be
//! name-shaped.

/// Upper bound on name-part count for the bitmask-based symbol
/// pairing in [`crate::names::pairing`]. Inputs beyond this
/// short-circuit to the empty-only fallback; coverage tracking needs
/// to fit in a `u64`.
pub const MAX_PARTS: usize = 64;

/// Per-side character cap for the character-level edit-distance DP in
/// [`crate::names::compare`]. The cost matrix is `O(left·right)`, so
/// an uncapped pair of long strings allocates hundreds of MB and
/// seconds of CPU on a single call (issue #230). Matches the
/// Python-side `RR_MAX_NAME_LENGTH` default so both surfaces truncate
/// alike.
pub const MAX_NAME_LENGTH: usize = 384;
