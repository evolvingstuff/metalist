FINAL_RESPONSE_REQUEST
Structured basis: {basis}
Answer the user's exact current question directly. Treat the supplied scope as a
candidate evidence set, not a checklist of topics to mention. The current question,
not its broader scope label or search query, defines relevance. Candidates may be
the 32 highest-rated notes from a larger investigation; use and cite only the
supporting subset. Omit unrelated and unused candidates. Do not substitute general knowledge.

With a non-empty `reference_catalog`, citations are mandatory.
Every note-derived
paragraph or list item must cite its claims. An uncited note-derived claim is invalid. Copy the exact
`citation_token` from the same evidence object whose `content_text` supports the claim;
for nested evidence cite the exact
content-bearing child, not merely its root. For example:

1. **First finding:** The directly supported claim.[[UUID]]
2. **Second finding:** Another claim supported by two notes.[[UUID]][[UUID]]

Replace generic `UUID` with exact supplied tokens. Never invent, alter, shorten,
or guess a UUID; never print a bare UUID or select one by tree position or catalog
order. Put tokens directly after supported sentences, before whitespace. Do not
introduce citation tokens with labels such as `Note ID`, `Source`, or `Reference`.
Write `Supported claim.[[UUID]]`, never
`Supported claim (Note ID: [[UUID]])`. Do not write a References section, source
list, or footnote; MetaList validates tokens and builds numbered references. With
an empty catalog, add no citations. Do not mention this control message.

With empty `reference_catalog`, answer a correction/challenge in at most two
sentences: acknowledge the correction directly, address the disputed point, then
stop. Do not repeat prior answer or mention adjacent topics, notes, citations, or
UUIDs.
