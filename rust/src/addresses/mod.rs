// Address analysis and comparison — tokenize and classify address
// strings into `Address { tokens, scripts }`, and score string
// pairs for similarity.

pub mod analyze;
pub mod compare;
pub mod fingerprint;
pub mod tagger;
pub mod token;
