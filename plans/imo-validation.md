---
description: Fix rigour.ids.IMO (issue #249) — first-match extraction grabs stray digit runs, zfill turns short garbage into checksum-valid IMOs (all-zero included), and one is_valid conflates the vessel and company checksum schemes. Plan for longest-run extraction, a 5-digit floor, all-zero rejection, and is_valid_vessel/is_valid_company scheme helpers on the single IMO format.
date: 2026-07-17
tags: [rigour, ids, imo, validation, zavod, vessels]
---

# IMO validation hardening (issue #249)

## Problem

`rigour/ids/imo.py` is the checksum gate behind zavod's global entity-ID minting
(`make_vessel_imo_id` / `make_org_imo_id` → `imo-vsl-…` / `imo-org-…`). Anything it
wrongly blesses becomes a silent cross-dataset entity merge. Three verified defects
(all reproduced against rigour 2.2.0):

1. **First-match extraction.** `IMO_RE = \b(IMO)?(\d{1,7})\b` + `.search()` takes the
   *first* 1–7-digit run anywhere in the string. `"Flag 12, IMO 9289518"` →
   candidate `12`, and after zfill `0000012` *passes the vessel checksum*
   (`1×2 = 2`), so `normalize` returns `IMO0000012` and the real IMO is ignored.
2. **zfill amplifies garbage.** Any 1–7-digit run is left-padded to 7 digits before
   the checksum. `0` → `0000000` passes (trivially: `0 == 0`), so every dataset with
   a `0`/`000` placeholder converges on one phantom vessel. Because `is_valid`
   accepts *either* checksum scheme, **190 of the integers 0–999 validate** (~19%).
3. **Scheme conflation.** One `is_valid` tries the vessel scheme, then the company
   scheme. A company number validates as a vessel number and vice versa; callers
   minting scheme-specific IDs can't be strict.

The zero-padding itself is deliberate (commit `44c050c`): sources strip leading
zeros, so `912681` should validate as `0912681`. The defect is padding *arbitrarily
short* runs, not padding per se.

## Consumers and compatibility constraints

- **followthemoney** — `Vessel.imoNumber` and `Organization.imoNumber` both declare
  `format: imo`; `IdentifierType.clean_text` routes through `IMO.normalize`. One
  registry name currently serves both schemes.
- **nomenklatura** — `logic_v1/identifiers.py` uses `IMO.normalize` for bidirectional
  `imoNumber` matching. `IMO.STRONG = True`, so a shared (bogus) IMO is treated as
  strong match evidence — false-valids are expensive here.
- **zavod** — `helpers/vessels.py` `_imo_id_key` uses `IMO.normalize`; invalid values
  fall back to `slugify(raw)`. The `ua/war_sanctions` crawler keys vessels and
  ship-management orgs this way.

## Design

### 1. Longest-run selection (fixes defect 1)

Selection and validation are two separate jobs the current code conflates. For
*selection*, replace single `.search()` with longest-run-wins:

- Candidates: maximal digit runs of length 5–7 (runs of 8+ digits — MMSIs,
  concatenations — are ignored as candidates, preserving `"91268191"` → `None`;
  runs of ≤ 4 digits are placeholder garbage per §2). Both bounds live in the
  regex: `(IMO[\s:.#-]*)?(?<!\d)(\d{5,7})(?!\d)`.
- One preference order over all candidates: **longer before shorter**, then
  `IMO`-prefixed before bare, then positional. Return the first candidate that
  survives validation (§2) and the scheme-appropriate checksum; `None`/`False`
  if none does. Implementation is a single `sorted()` over `finditer` matches
  with key `(-len, unprefixed, start)`.

`"Flag 12, IMO 9289518"` → `9289518` wins on length alone. A string containing
only an invalid IMO (`"IMO 9289519"`) still correctly returns `None`. Fall-through
keeps multi-value fields working (`"9289519 / 9126819"` finds the valid one), and
crosses lengths (a padded shorter run can win when every longer run fails).

Considered and rejected (2026-07-17): a tier rule where a checksum-failing
7-digit run vetoes shorter runs beside it (rationale: zero-stripping happens to
whole field values, and a random padded run passes a checksum ~18% of the time).
Dropped for simplicity — the shape it guards against is rare, and the flat
preference order keeps extraction a single obvious pass.

### 2. Length floor + all-zero rejection (fixes defect 2)

Longest-run selection alone cannot replace a floor: in a garbage-only field
(`"0"`, `"12"`, a placeholder), the longest run *is* the garbage, and after zfill
~18% of random short runs pass one of the two checksums (measured over 20k
samples — the lottery odds are length-independent, so only a floor closes it).

At validation time, for **both schemes** (decision 2026-07-17):

- Minimum **5 digits**: up to two stripped leading zeros. 5–6-digit values
  zero-pad to seven; 7-digit values pass through; `0`, `12`, `9126` are
  rejected.
- Reject `0000000` explicitly (and therefore any all-zero run after zfill).
- `is_valid`/`normalize` accept either scheme's checksum (~18% lottery on a
  random padded run); the scheme-restricted helpers (§3) accept one (~10%).

`912681` → `IMO0912681` keeps working, and this drops the 0–999 acceptance rate
from 19% to 0.

Considered and rejected (2026-07-17): restricting padding to the company scheme
on the grounds that issued vessel number ranges (LR historic 5xxxxx–9xxxxx,
modern 1xxxxx/2xxxxx six-digit blocks) contain no leading zeros. Rejected
because zero-padded vessel IMOs are observed in real source data regardless —
rigour validates what data providers actually emit, not the issuance spec.

### 3. Scheme-specific checks (fixes defect 3)

Split the checksum into two internal predicates (`_vessel_checksum`,
`_company_checksum`). **Decision (2026-07-17): no new registry formats** — the
identifier type system stays as-is. Instead, `IMO` (unchanged registry name
`"imo"`, still accepting either scheme for FtM/nomenklatura back-compat) gains
two classmethod helpers:

- `IMO.is_valid_vessel(text)` — vessel checksum scheme only.
- `IMO.is_valid_company(text)` — company checksum scheme only.

Both run the same extraction pipeline (§1–2), restricted to one checksum.
Callers minting scheme-specific IDs use `IMO.normalize` for the canonical form
and gate on the scheme helper.

### 4. Implementation shape

- One internal helper `_extract(text, checksums) -> Optional[str]` returning
  the canonical 7-digit string; `normalize` wraps it with the `IMO` prefix;
  `is_valid` / `is_valid_vessel` / `is_valid_company` pass the appropriate
  checksum tuple (drops the current duplicated search/zfill logic).
- `format()` unchanged.
- Docstrings: document the padding rule and the candidate preference once on
  the `IMO` class docstring; the helpers link back to it.

### 5. Tests

Extend `tests/ids/test_imo.py`:

- Issue repros: `"Flag 12, IMO 9289518"` → `IMO9289518`; `"0"`, `"000"`,
  `"0000000"` → invalid/None; `"IMO 9289519"` and `"9289519"` both → None.
- Padding floor: `"912681"` → `IMO0912681` stays green; a checksum-valid
  5-digit value (two stripped zeros) normalizes under its scheme; a 4-digit
  value never does.
- Scheme helpers: a company number (`6459297`) passes `is_valid_company` but
  not `is_valid_vessel`, and vice versa for `9126819`; `is_valid` accepts both.
- Selection: longest run beats an earlier shorter run (`"Flag 12, IMO 9289518"`);
  fall-through across two 7-digit runs where only the second is valid; 8+-digit
  runs ignored (`"91268191"` → None, MMSI next to a valid IMO still resolves).

## Behaviour changes (downstream-visible)

| Input | Before | After |
|---|---|---|
| `"0"`, `"000"`, `"0000000"` | `IMO0000000` | `None` |
| 1–4-digit runs (`"12"`, `"9126"`…) | ~19% validate | `None` |
| 5–6-digit runs | ~19% validate | zfill + scheme checksum (~18% union, ~10% per scheme) |
| `"912681"` (valid after pad) | `IMO0912681` | `IMO0912681` (unchanged) |
| `"Flag 12, IMO 9289518"` | `IMO0000012` | `IMO9289518` |

Datasets that previously minted `imo-vsl-0000000`-style IDs will re-key those
entities on next crawl. **Decision (2026-07-17): re-keying is accepted** — stale
resolver/dedupe links against the phantom entities are tolerable; a release-note
mention is still worthwhile.

## Downstream follow-ups (separate PRs, listed for context)

- **zavod**: gate `make_vessel_imo_id` on `IMO.is_valid_vessel` and
  `make_org_imo_id` on `IMO.is_valid_company` before using the normalized
  value. Also consider normalising the slug fallback so `"IMO 9289519"` and
  `"9289519"` produce the same fallback key (strip an `IMO` prefix before
  `slugify`).

## Open questions

1. ~~Floor height.~~ **Decided (2026-07-17): 5 digits, both schemes.**
   Zero-padded vessel IMOs are observed in practice, so padding applies to
   vessel and company numbers alike (see the rejected alternative in §2).
2. ~~Registry split (`imo-vessel` / `imo-company` formats).~~ **Decided
   (2026-07-17): no.** The type system is not expanded; scheme checks are
   classmethod helpers on `IMO`. `STRONG = True` stays on the single format.
