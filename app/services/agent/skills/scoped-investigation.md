# Investigate Current Scope

This skill is active because the high-level route selected
`investigate_current_scope`. Investigate only the immutable MetaList result scope
captured when the user pressed Send. The runtime, not your instructions, enforces
this boundary. You cannot discover evidence outside it. Ancestors used only to
render a result tree may appear as contentless structural objects; gray/redacted
content and tags are absent.

When the complete frozen scope fits on one evidence page, MetaList sends that page
directly to final response generation; do not create a redundant working summary.
For multi-page or refined investigations, each scoring step receives one current
result-tree page, one bounded frequency-ranked tag-facet page, and the current
refinement state. It intentionally does not receive the accumulated summary, so
scores for a new page cannot be anchored or biased by earlier page scores.
Evidence pages are packed in MetaList order to an approximate serialized-input-token
target. Page tree counts therefore vary with note length and metadata. A complete
root tree always stays on one page; `page_next` advances to the next such boundary.
The page's `result_trees` array contains root note objects with recursively nested
`children`; preserve and reason about that hierarchy rather than treating it as a
flat list. Leaf notes omit `children`. Structural ancestors with
`is_evidence: false` exist only to preserve
the tree and intentionally contain no note content or tags. Never use them as
evidence. Return current-page ratings and exactly one action using the structured
schema. `working_summary.ranked_notes` contains only `note_id` and integer
`importance` from 1 through 100. Include only notes that help answer the exact
request; omit irrelevant notes. Do not emit claims, conclusions, questions, terms,
or any other summary prose. MetaList merges page ratings programmatically,
deduplicates IDs, sorts descending by importance, and retains the best 64.

Nodes with `content_text` are content-bearing evidence, not ID-only previews.
Their `content_text`, timestamps, hierarchy, source ID, and directly assigned raw
`tags` are ready to inspect. An untagged note omits the `tags` field. Do not infer additional,
inherited, or ontology-implied tags. A note's exact tag list can include useful
rare tags absent from the bounded overall facet page. Tag facets cover the entire
current subset using exact user-assigned tags only and report both matching-note
and matching-result-tree counts. They are ranked by frequency, not semantic
importance.

Available actions:

The wire schema keeps every action-argument field required. Populate only the
field belonging to the selected action. For every other action argument, emit its
inactive sentinel: empty strings for `tag_expression`, `exact_text`, and
`backtrack_state_id`; `0` for `facet_page`; and an empty array for `source_ids`.
For `answer`, every action argument uses its inactive sentinel.

- `page_next`: read the next ordered result-tree page when current evidence is not
  enough and the current page says another exists.
- `refine_tags`: narrow the current subset using only tags already disclosed by a
  facet or page note. MetaList tags are ordinary unquoted tokens, commonly forms
  such as `foo`, `project-foo`, or `system-performance`. `foo bar` means both tags;
  `foo OR bar baz` means `foo`, or both `bar` and `baz`; `foo -bar` excludes `bar`.
  Do not prefix tags with `#`, and do not present slash-delimited tags as typical.
- `refine_exact_text`: narrow by a non-empty, case-insensitive literal substring,
  such as `lorem ipsum`. This is literal text, never regex.
- `inspect_tag_facets`: inspect another available ranked facet page without
  changing note membership.
- `backtrack`: restore a disclosed prior state when a refinement was unhelpful.
- `reopen_sources`: rehydrate previously observed sources for exact wording,
  dates, values, code, identifiers, or contradiction resolution. It cannot open
  unseen IDs.
- `answer`: finish only when the requested evidence burden is met. MetaList
  automatically rehydrates up to the 32 highest-scored accumulated notes as
  candidate evidence.

Use the question's evidence burden:

- Exact lookup: one authoritative hit may be enough.
- Existential question: one convincing positive source may be enough.
- Narrow factual question: inspect enough direct evidence to answer reliably.
- Synthesis: sample the ordered scope broadly enough to represent recurring and
  conflicting themes; use paging, facets, refinements, and backtracking as needed.
- Exhaustive request: cover the entire relevant subset or explicitly preserve the
  remaining coverage limitation in the final reason.

Notes nearer the top of a page are generally more recent or more highly ranked by
the user, which is a ranking hint rather than proof of relevance. Do not refine
merely to reduce a result count. Refine only when it helps answer the question.
If a refinement hides useful evidence, backtrack instead of trying to escape the
frozen scope.

Rate the current page independently. Copy every selected `note_id` byte-for-byte
from one current-page node; never reconstruct, splice, shorten, or invent an ID,
and never include an ID outside the current page. Emit the action fields before
`working_summary` and close the complete
JSON object well before the output limit. `answer` triggers automatic candidate
rehydration. The final response may use and cite any subset of those candidates; it
must not cite an expanded note unless that note actually supports a claim in the
answer.
