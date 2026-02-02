# PLAN: Search Suggestions (Tag-Only)

## Goal
Add fast tag-only search suggestions. Suggestions are ordered by tag co-occurrence with all existing tag tokens in the search query, using a Jaccard-like score, with strict priority for matches that co-occur with more anchors. Prefix matches for the currently-typed partial tag appear even if no overlap.

## Scope
- Search box suggestions only (no tag-bar suggestions).
- Suggestions are tags only (no text suggestions).
- Works with queries that include quoted text; suggestions use tag tokens only.

## Requirements (Confirmed)
- Use ALL existing tag tokens in the query as anchors.
- Strict ordering by overlap count: tags co-occurring with all anchors rank above any that co-occur with fewer anchors.
- Within each overlap group, rank by Jaccard similarity (or equivalent co-occurrence score); tie-break by stable alpha.
- Always include prefix matches for the current partial tag token, even if no overlap (these appear at the bottom).
- No counts displayed in UI for now.

## Plan
1. **Inventory current search parsing + tag index**
   - Identify how search tokens are parsed (tag tokens vs quoted strings).
   - Locate existing tag index structures used by search.

2. **Design in-memory co-occurrence structures**
   - On startup, build:
     - `tag -> set(note_id)` (already exists or derive from index).
     - `tag -> count` (note frequency).
     - Optional `tag -> bitset` for faster intersections (depending on data size and existing utilities).
   - Maintain an incremental update path for tag edits (add/remove tags on note change).

3. **Server-side suggestion API**
   - Add an endpoint or extend existing search endpoint to return suggestions.
   - Input: full query string.
   - Output: ordered list of tag suggestions (strings).

4. **Suggestion algorithm**
   - Parse query into:
     - `anchor_tags`: existing complete tag tokens.
     - `partial_prefix`: current partial tag token (if any).
   - Compute candidates by overlap count:
     - For each candidate tag, compute how many anchors co-occur.
     - Strictly order by overlap count desc.
     - Within group, score by Jaccard: |N(tag) ∩ N(anchors)| / |N(tag) ∪ N(anchors)|.
   - Append prefix-only completions (for `partial_prefix`) that are not already included, ordered alpha.

5. **Client integration**
   - Wire suggestions into the search box UI (dropdown).
   - Trigger on input changes; debounced.
   - Ensure prefix token handling with quoted text in query.

6. **Tests + sanity**
   - Unit tests for parsing + ranking (including quoted strings, multi-anchor ordering, prefix-only completions).
   - Verify updates when tags on notes change.

## Success Criteria
- Search suggestions are tag-only and appear for queries like `Socrates "ancient greece" phil`.
- Results strictly prioritize tags that co-occur with all anchors over fewer anchors.
- Prefix completion appears even with zero co-occurrence.
- No noticeable latency regression for large note sets.
