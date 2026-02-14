# PLAN

## Goal
Restore external HTML paste behavior to be at least as good as legacy (fidelity-first), while preserving a clear security boundary.

## Why This Plan Changed
- Regex-only inference was insufficient.
- Visual output regressed vs legacy despite safe sanitization.
- Next attempt must be evidence-driven, not inferred.

## Non-Goals
- No changes to internal note clipboard copy/paste behavior.
- No rewrite of existing stored note HTML.
- No broad visual redesign in MetaList rendering.

## Hard Requirements
1. Legacy fidelity must be measured against real legacy output examples.
2. Security constraints must be explicit and test-backed.
3. No implementation proceeds past each gate without your approval.

## Gate-Based Workflow

### Gate 1: Legacy Source of Truth
Objective: identify exact legacy sanitizer behavior.

Tasks:
1. Locate legacy sanitizer implementation (file/commit/repo) and document:
- tag/attribute handling
- style handling
- URL and entity handling
- image handling
- any browser-specific parsing behavior
2. If legacy code is unavailable, build a frozen fixture corpus from known before/after examples you provide.

Exit criteria:
- One canonical source selected: either legacy code or approved fixture corpus.
- You approve the source of truth.

### Gate 2: Acceptance Corpus + Diff Rules
Objective: define what “good” means before coding.

Tasks:
1. Build test fixtures:
- raw pasted HTML input
- expected normalized output HTML
- screenshot-level notes for critical visual cases (threads, badges, links, images)
2. Define tolerable differences from legacy (if any), explicitly:
- acceptable: minor whitespace normalization
- not acceptable: missing images, collapsed hierarchy, lost quoting/list structure

Exit criteria:
- Fixture set checked in and approved.
- Pass/fail criteria agreed.

### Gate 3: Security Contract
Objective: lock security constraints independent of fidelity.

Tasks:
1. Specify blocked vectors:
- executable URLs (`javascript:`, unsafe `data:`)
- event handlers (`on*`)
- script/style/embed/iframe/object/form execution surfaces
- dangerous CSS payloads (`url(...)`, `expression(...)`, imports/bindings)
2. Specify allowed image policy.

Exit criteria:
- Security policy documented and approved.

### Gate 4: Implementation (Minimal Delta)
Objective: implement smallest change set to hit legacy parity + security contract.

Tasks:
1. Build sanitizer as a deterministic pipeline:
- parse
- normalize
- legacy-parity transforms
- security enforcement
2. Integrate only at external paste insertion point.
3. Keep cursor/selection and `ModeContext` updates consistent.

Exit criteria:
- Fixture tests pass.
- Security tests pass.

### Gate 5: Verification + Sign-off
Objective: confirm with real-world paste cases.

Tasks:
1. Run automated tests and `./sanitycheck/run`.
2. Manual test set:
- Reddit comments/threads
- posts with badges and inline metadata
- embedded images/screenshots
- quoted/indented/threaded structures
3. Record before/after against fixture corpus.

Exit criteria:
- You confirm parity is acceptable.

## Implementation Notes (for Gate 4)
- Prefer preserving structure and semantic hierarchy over aggressive style reconstruction.
- Do not rely on class-based site CSS for fidelity; preserve structural HTML and safe inline declarations where needed.
- Image support is mandatory for parity-sensitive cases.

## Deliverables
1. Updated sanitizer module with deterministic behavior.
2. Fixture-driven unit tests (fidelity + security).
3. Documentation update for paste behavior and constraints.

## Validation Commands
- `node --test tests/unit/...`
- `./sanitycheck/run`

## Current Blocker
- Missing explicit legacy source of truth in repo.

## Immediate Next Step
- You provide one of:
1. Legacy sanitizer file/path or commit hash.
2. A set of raw clipboard HTML samples + expected output screenshots/HTML.
