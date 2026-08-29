# Search Notes

This skill is active because the agent selected `search_notes`. Produce the
single focused MetaList query and one-based result page to execute next through
the structured response schema supplied by the inference layer.

The final user message is the current request. Use earlier conversation only when
the current request explicitly depends on it, such as a follow-up that refers back
to an earlier subject. A topic change does not require an exclusion. For a new
topic, start at page `1` and use only terms supported by that current topic. Never
carry an earlier topic into a new query merely to negate it. Add a negative term
only when the current request asks for that exclusion or an in-run search result
establishes a specific false-positive pattern; explain that basis in `reason`.

MetaList search syntax:

- Unquoted terms match tags. `foo bar` requires both the `foo` and `bar` tags.
- Quoted phrases match exact note text. `"lorem ipsum"` requires that phrase.
- A leading minus sign excludes a tag or quoted phrase. `foo -bar` requires
  `foo` and excludes `bar`; `foo -"lorem ipsum"` excludes that text.
- Uppercase `OR` separates clauses. `foo OR bar baz` matches either `foo`, or
  both `bar` and `baz`.
- Every query and every `OR` clause must contain at least one positive tag or
  quoted-text term. Never emit `-foo`, `-"lorem ipsum"`, or `foo OR -bar`.

Prefer the narrowest query supported by the request and available transient
tool results. Never copy an unrelated conversational sentence into the query.
For a broad topical request, completeness requires searching both tags and note
text unless the user explicitly asks for tag-only or text-only scope. Combine the
tag form with the quoted-text form in the first query: use `foo OR "foo"` for a
one-word topic, and `foo bar OR "foo bar"` for a multi-word topic. Do not wait for
a second search to add the other form. A request specifically about a tag may use
`foo`; a request specifically about an exact phrase may use `"lorem ipsum"`.
Use page `1` for every new or refined query. If a prior result is relevant but
insufficient and says `has_next_page: true`, repeat the exact same query with its
`next_page` value. Never skip pages or request a page that the result says does
not exist. Examples: query `foo`, page `1`; query `foo OR bar baz`, page `1`;
after a result for `foo` reports `next_page: 2`, query `foo`, page `2`.
Broad synthesis requests normally require additional relevant pages when
`has_next_page` is true. Continue the same query in order rather than treating the
first page as the complete result set. If later orchestration stops before all
pages are retrieved, the final answer must say which pages informed the answer.
When a relevant result reports `has_next_page: false`, do not issue another search
merely to narrow or reduce the result count. A different query is justified only
by specifically identified missing evidence or a concrete false-positive pattern,
and `reason` must name that need.

Each result page contains at most the user's configured number of top-level result
trees and includes their matching note nodes. `matched_count` is the number of top-level result trees, while
`matched_note_count` is the number of matching note nodes across all pages.
Multiple matching nodes under one root therefore still count as one result tree.
These are content-bearing results, not ID-only previews: each returned note's
bounded content is already present in `notes[].content_text`, and `note_id` exists
for citation and navigation rather than to require a follow-up read.
Notes nearer the top of the returned page are generally more recent or more highly
ranked by the user. Use that ordering as a ranking hint, not proof of relevance:
the note content and metadata must still support the user's request.
Only matching nodes are included: non-matching children represented as gray
search-redaction bars in the UI are omitted completely. Each included note carries
its explicit tags, hierarchy IDs, created/updated timestamps, and truncation or
redaction flags. Never infer omitted, truncated, or redacted content. Do not use a
redundant read-by-ID action merely to bypass a page or per-note limit.
