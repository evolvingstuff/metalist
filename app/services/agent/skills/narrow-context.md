# Narrow Context

This skill is active because the frozen MetaList result scope is substantially
larger than the configured investigation target. Propose an ordered list of
exact raw tags that are likely to retain the notes needed to answer the current
user request while reducing the total evidence-token size.

- The frozen user search is an immutable outer boundary. Narrowing may only
  remove notes from that scope; it must never broaden or replace the search.
- Return only tags explicitly listed in `tag_facets`. Do not invent tags, add
  `#`, quote tags, use exclusions, or write a search expression.
- Tags already positively required by every branch of the frozen user search are
  listed separately and removed from `tag_facets`; proposing one again cannot
  narrow the scope.
- Order tags cumulatively: MetaList tests the first tag, then the first two tags
  together, then the first three together, and so on.
- Put the most semantically useful and least destructive constraint first.
- When useful, aim for `suggested_proposed_tags` exact tags so MetaList can
  measure progressive contraction toward the target instead of receiving an
  unnecessarily short one-item plan. This is guidance, not a schema rule: one
  tag remains valid, including when it is the only legitimate candidate.
- Formatting and structural tags beginning with `@` are not semantic narrowing
  candidates and are excluded from `tag_facets`.
- Facet counts are independent counts within the frozen scope, not forecasts for
  cumulative combinations. MetaList measures every cumulative prefix itself,
  continuing through the proposed list until a prefix produces zero results.
- Raw tags inherit down the note hierarchy for matching even though inherited
  tags are not repeated in each note payload. A retained match keeps its
  descendants and the structural ancestor path needed to display it, but not
  unrelated siblings. All cumulative tags must be satisfied along the same
  note-to-ancestor inheritance path; tags found only on sibling branches do not
  satisfy an AND constraint.
- `synonyms` communicate tag meaning (for example `ML3 = MetaList`). They do not
  authorize returning a synonym that is absent from the available exact tags.
- MetaList selects the closest non-empty cumulative prefix at or below the
  target. If every proposed prefix remains above the target, it retains the
  smallest non-empty result reached. Zero-result refinements are rejected.
