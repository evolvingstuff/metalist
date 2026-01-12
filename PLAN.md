# PLAN.md — In-Memory Search & Ontology Engine (Python Server)

This document is the authoritative implementation plan for the PKMS server-side
search system.

It is written for a **Python server**, with **SQLite used only for encrypted
persistence**, and **all search/indexing data held entirely in memory** during
runtime.

Search always operates on the **current state of notes only**.
Undo/redo history is ephemeral and does NOT participate in search.

---

## 1. Core Design Principles

1. **Search must be fast and predictable**
   - No ontology traversal at query time
   - No regex execution at query time
   - Queries reduce to set algebra + verification

2. **Do expensive work early**
   - On server startup
   - On ontology rule changes
   - On note edits (for that note only)

3. **Everything searchable is precomputed**
   - Notes store their implied tags explicitly
   - Search never walks implication chains

4. **Correctness beats cleverness**
   - False positives are acceptable
   - False negatives are not
   - Verification is always performed

---

## 0. Scope

### v1 (now)
- Build an in-memory search index for:
  - Tag terms (from the tag bar)
  - Quoted text terms (substring search via trigram candidate generation + verification)
- Update the index incrementally on note add/edit/delete.
- Use the index to drive `/api2/notes/view` filtering without affecting non-search behavior.

Notes:
- Ontology / implication rules are explicitly out of scope for v1.
- Roaring bitmaps are the target representation, but in the absence of a roaring
  dependency we can start with an abstraction backed by Python sets.

### Future work
- Ontology / implications.
- Swap Python-set bitmaps to Roaring bitmaps.

---

## 2. Identity Model

### External IDs
- Notes are externally identified by UUIDs
- SQLite stores UUIDs only

### Internal Dense IDs (in-memory only)

On startup, each current note is assigned a dense integer ID:

    noteId: 0 .. N-1

Mappings:
- uuid_to_id: Dict[UUID, int]
- id_to_uuid: List[UUID]

All indexes operate on noteId.

Dense IDs are **not persisted** and are rebuilt on every startup.

---

## 3. In-Memory Data Model

### Per-note state (keyed by noteId)
- html: str  
- search_text: str  (derived, normalized plain text)  
- explicit_tags: Set[tagId]  
- effective_tags: Set[tagId]  
- trigrams: Set[triKey]  

### Global indexes

#### Tag index
    tag_notes: Dict[tagId, RoaringBitmap]

Contains **effective tags only**.

#### Trigram index
    tri_notes: Dict[triKey, RoaringBitmap]

Used only for substring candidate generation.

---

## 4. Roaring Bitmaps (Python)

### What “roaring” means
A Roaring Bitmap is a compressed set of non-negative integers supporting:
- intersection (AND)
- union (OR)
- difference (AND NOT)
- cardinality
- fast iteration

They are ideal for representing sets of noteIds.

### Python libraries

Preferred:
- pyroaring

Fallback:
- roaringbitmap

Required operations:
- add(noteId)
- remove(noteId)
- bitmap & other
- bitmap | other
- bitmap - other
- len(bitmap)
- iteration over members

If roaring is unavailable initially:
- use sorted lists of integers
- keep the interface abstract so roaring can be swapped later

---

## 5. HTML → Search Text Extraction

### Goal
If stored HTML is:

    <span>Hello</span> world

Then searching for:

    "Hello world"

must match.

### Extraction rules
1. Parse HTML using a real HTML parser (never regex)
2. Ignore script, style, and noscript elements
3. Extract visible text nodes in document order
4. Insert whitespace boundaries between block-level elements
5. Decode HTML entities

### Normalization
- Convert all whitespace (spaces, tabs, newlines, NBSP) to ASCII space
- Collapse runs of spaces to one
- Trim leading and trailing spaces

The result is stored as `search_text` and used for:
- trigram indexing
- substring verification

---

## 6. Unicode Canonicalization for Trigrams

### Problem
Unicode and emoji can explode the trigram vocabulary.

### Solution
Before trigram extraction, canonicalize characters:
- Keep ASCII characters as-is
- Map all other Unicode code points to a single sentinel character
  (use a Private Use Area code point such as \uE000)

Important:
- Canonicalize BOTH note search_text and query strings identically
- This guarantees no false negatives

False positives are expected and removed during verification.

---

## 7. Trigram Index

### Definition
A trigram is any sequence of 3 consecutive characters in the canonicalized text.

Example:
    "search systems"
Produces:
    "sea", "ear", "arc", "rch", "ch ", "h s", " sy", "sys", ...

### Index structure
    tri_notes: Dict[triKey, RoaringBitmap]

Each triKey maps to all noteIds containing that trigram.

### Building the index (per note)
1. Canonicalize search_text
2. Generate all overlapping trigrams
3. Store unique trigrams in note.trigrams
4. Add noteId to tri_notes[tri]

### Updating on note edit
- Diff old vs new trigram sets
- Remove noteId from removed trigrams
- Add noteId to added trigrams

### Querying with trigrams
If query length >= 3 characters:
1. Canonicalize query
2. Generate query trigrams
3. Intersect corresponding tri_notes bitmaps
4. Verify candidates with search_text.includes(query)

### Short query fallback
If query length < 3:
- Skip trigram index
- Verify directly against candidate set (or all notes)

---

## 8. Tag System

### Tag IDs
- tag_to_id: Dict[str, tagId]
- id_to_tag: List[str]

### Effective tags
Each note stores:
    effective_tags = explicit_tags ∪ implied_tags

The tag index always reflects effective_tags.

---

## 9. Ontology Rules

> Future work (not in v1).

### Rule categories

1. **Simple tag implications**
       A => B
   Used to build a transitive closure over tags.

2. **Complex rules**
       LHS (substring, regex, tag context) => RHS tag(s)

### Simple implication closure
- Build directed graph over tagIds
- Compute transitive closure per tag
- Store closure[tagId] = Set[tagId]

### Complex rules
Each rule compiles to:
- predicate(note) -> bool
- rhs_tags: List[tagId]

Predicates may test:
- substring presence in search_text
- regex match on search_text
- tag conjunctions (AND)

---

## 10. Rule Evaluation Strategy

> Future work (not in v1).

### On ontology rule change (add/edit/delete)
- Recompute simple implication closure
- Recompute effective_tags for ALL notes
- Rebuild tag_notes from scratch

This is allowed to be expensive.

### On note add/edit
- Re-evaluate complex rules for that note only
- Apply implication closure
- Diff old vs new effective_tags
- Update tag_notes incrementally

---

## 11. Query Execution

> Future work (not in v1).

### Steps
1. Start with ALL_NOTES bitmap
2. Apply required tag filters (AND)
3. Apply forbidden tag filters (AND NOT)
4. Apply quoted substring filters:
   - Use trigrams when length >= 3
   - Fallback scan when length < 3
5. Always verify with substring check
6. Return matching UUIDs

### Ordering
- Always intersect the smallest sets first
- Roaring cardinality can guide ordering

---

## 12. Startup Sequence

> Future work (not in v1).

1. Decrypt SQLite persistence
2. Load current notes
3. Assign dense noteIds
4. Extract search_text for each note
5. Build trigram index
6. Load ontology rules
7. Compute implication closure
8. Recompute effective_tags for all notes
9. Build tag_notes index

---

## 13. Explicit Non-Goals (v1)

- No historical version search
- No ranking or scoring
- No incremental ontology delete optimization
- No support-count bookkeeping

These can be added later if needed.

---

## 14. Summary

This design intentionally favors:
- simplicity over micro-optimizations
- correctness over cleverness
- predictable performance

Search reduces to:
- set algebra over roaring bitmaps
- followed by exact verification

All expensive logic is pushed out of the query path.
