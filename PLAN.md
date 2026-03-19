# PLAN

## Feature
Recency-weighted blank-search suggestions

## Goal
- When the search input is blank, reserve the top 3 suggestion slots for tags drawn from searches the user most recently searched and then meaningfully interacted with.
- A qualifying interaction is the first scroll after an executed search, or entering edit mode on a note while that search is active.
- Ranking must decay exponentially over time and persist per namespace.

## Current State
- `POST /api2/notes/search-suggestions` calls `search_index.suggest_tag_completions(query, limit)`.
- Blank-query suggestions are currently ranked by global tag frequency only.
- Search persistence today is limited to per-tab `searchQuery` and scroll metadata in `tab_state_store`; that state is in-memory and not suitable for long-term history.
- There is no current signal for "the user interacted with this search result set."

## Recommended Design

### 1. Add a persistent interacted-search sidecar store
- Add a dedicated per-namespace sidecar database alongside the main namespace DB:
  - example: `work.metalist.search-history.db`
- Keep this separate from:
  - the global launcher registry `namespaces.db`
  - the main notes DB
  - the files sidecar DB
- The sidecar should own its own schema and lifecycle.
- Suggested columns:
  - `query_key TEXT PRIMARY KEY`
  - `root_tag TEXT NOT NULL`
  - `tags_json TEXT NOT NULL`
  - `score REAL NOT NULL`
  - `query_encryption_nonce BLOB`
  - `query_encryption_tag BLOB`
  - `last_interacted_at TEXT NOT NULL`
  - `updated_at TEXT NOT NULL`
- Add a service that:
  - normalizes a search into the exact ordered sequence of non-negated tag terms
  - records interaction against that normalized query entry
  - applies lazy exponential decay on write/read using elapsed time since `last_interacted_at`
  - opportunistically prunes stale near-zero rows
  - can return the highest-scoring histories and flatten them into unique tag suggestions
- Encryption at rest:
  - follow the app's existing namespace encryption model
  - when the namespace is password-protected, persist `query_key`, `root_tag`, and `tags_json` encrypted with the namespace DEK
  - when the namespace is not password-protected, rows remain plaintext, matching current notes/file-storage behavior
  - `score` and timestamps can remain plaintext unless we decide they are also sensitive enough to encrypt

### 2. Normalize searches the way the legacy app conceptually did
- Parse with the existing search parser.
- Keep exact positive tag terms only.
- Ignore:
  - negated tags
  - quoted text terms
  - UUID-only searches
  - blank query
- Preserve order in the normalized key so `journal exercise` and `exercise journal` remain distinct histories.

### 3. Record only qualifying search interactions
- Add a dedicated endpoint such as `POST /api2/notes/search-interactions`.
- Payload:
  - `query`
  - `interactionType` with explicit values `scroll` or `edit`
- Server rules:
  - require a complete executed query from the client
  - require that the executed search currently has results
  - normalize the query using the rule above
  - ignore normalized histories whose tags no longer exist in `search_index`
- Legacy difference:
  - the old app credited on qualifying rendered search changes
  - this feature should credit only after user interaction, so we do not need render-based crediting

### 4. Add client-side interaction gating and dedupe
- Add a small client-only tracker keyed by `tabId + executedSearchQuery`.
- Reset the tracker whenever the executed search changes.
- Record at most one qualifying interaction per executed query per tab until the query changes.
- Qualifying events:
  - first non-zero scroll after that search executes
  - first note-selection/edit transition while that search is active
- Legacy anti-double-count note:
  - the old app had a special decrement rule for prefix-extension typing through intermediary exact tags
  - phase 1 should omit that unless testing shows interaction-gated queries still over-credit partial exact tags

### 5. Blend interaction recency into blank-search suggestions only
- Keep non-blank suggestion behavior exactly as it is today in phase 1.
- For blank query:
  - fetch the existing base suggestions
  - fetch the top decayed interacted-search histories
  - flatten them in score order into unique tag suggestions
  - place up to 3 history-derived tags first
  - dedupe against the base suggestions
  - fill remaining slots with the current ranking
- This preserves a clean path to restoring the richer legacy overlap behavior later for non-empty searches with few parsed terms.

### 6. Multi-term search policy
- Search suggestions are tag-only, so we should not try to surface a raw phrase like `journal exercise`.
- Recommended initial rule:
  - store the full normalized positive-tag sequence as one history entry
  - when blank query suggestions need top slots, flatten high-scoring histories into unique tags
- Examples:
  - `journal exercise` -> one history entry with tags `["journal", "exercise"]`
  - `journal -todo "weekly review"` -> one history entry with tags `["journal"]`
- Reasoning:
  - preserves co-occurrence information instead of throwing it away
  - matches the legacy model you described
  - keeps the door open for overlap-based non-empty suggestion ranking later

## Legacy Behavior To Keep vs Change
- Keep:
  - normalized exact positive-tag query history
  - ranking histories by overlap first and score second as a future-compatible direction
  - fallback to plain included-tag frequency after history-derived suggestions
  - hard separation between namespace runtime metadata and search-history data
- Change:
  - decay should be time-based, not event-count-based
  - credit should require interaction, not just rendered search changes
  - phase 1 scope should be blank-query top-3 promotion only unless we explicitly expand it

## Open Decisions For Discussion
- Decay half-life: start at 7 days, 14 days, or another explicit value?
- Scroll threshold: any non-zero scroll, or a larger threshold such as 50 px?
- Interaction cap: one record per executed query per tab only, or allow another credit after a cooldown?
- Should phase 1 stay blank-query-only, or should we also restore the legacy overlap weighting for non-empty searches with fewer than 5 parsed terms?
- Do we want the old prefix-extension anti-double-count rule back, or is interaction gating enough?

## Tests
- Backend unit tests for:
  - decay math
  - blank-query top-3 promotion
  - stale or nonexistent tag filtering
  - multi-term history normalization
  - flattening unique tags from ranked histories
  - sidecar DB initialization/bootstrap
  - encrypted row round-trip when namespace encryption is enabled
  - ignoring blank, negative-only, quoted-text-only, and UUID-only searches
- Client tests or targeted manual verification for:
  - no interaction recorded on mere typing
  - first scroll records once
  - note click into edit records once
  - repeated scroll/click under the same executed query does not spam writes
  - a new executed query resets eligibility

## Docs To Update During Implementation
- `docs/ui/controls.md`
- `docs/ui/search-semantics.md`
- `docs/AI-SUMMARY.md` if the new store/service should be reflected in the architecture summary

## Success Criteria
- Blank search shows up to 3 recency-prioritized tags first.
- Those tags come only from searches the user later scrolled or edited within.
- Ranking decays over time and persists across reloads/restarts.
- Existing non-blank suggestion behavior stays unchanged.
