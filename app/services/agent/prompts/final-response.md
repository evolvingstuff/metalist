FINAL_RESPONSE_REQUEST
Structured basis: {basis}
Answer the user's exact current question directly. Treat the supplied scope as a
candidate evidence set, not a checklist of topics to mention. The current question,
not the broader scope label or search query, defines relevance. Include only
evidence that directly helps answer it and omit unrelated evidence even when it
shares the broader topic. Do not substitute general knowledge.

When `reference_catalog` is non-empty, citations are mandatory. Every note-derived
paragraph or list item must contain at least one exact citation token immediately
after the claim it supports. An uncited note-derived claim is invalid. Copy the
`citation_token` from the same evidence object whose `content_text` supports that
claim. Cite each distinct claim with its direct source or sources; reuse a token
when the same note supports multiple claims. When evidence is nested, copy the
token from the exact content-bearing child note, not merely its enclosing root.
For example:

1. **First finding:** The directly supported claim.[[UUID]]
2. **Second finding:** Another claim supported by two notes.[[UUID]][[UUID]]

Replace each generic `UUID` above by copying an exact supplied `[[UUID]]` token.
Never invent, alter, shorten, or guess a UUID, never print a bare UUID, and never
choose a token merely from tree position or catalog order. Do not create a
References section. MetaList validates the exact tokens, converts them to numbered
superscript links, and builds References programmatically. Citation tokens are
inline markers only. Put each token directly after the supported sentence, before
any following whitespace, without parentheses or introductory prose. Do not
introduce citation tokens with labels such as `Note ID`, `Note IDs`, `Source`, or
`Reference`; write `Supported claim.[[UUID]]`, never
`Supported claim (Note ID: [[UUID]])`. Never append a citation token plus source
text, a footnote, a source list, or a References heading. End after the answer
itself. When the catalog is empty, do not add citations. Do not mention this control
message.

With empty `reference_catalog`, answer a correction/challenge in at most two
sentences: acknowledge the correction directly, address the disputed point, then
stop. Do not repeat prior answer or mention adjacent topics, notes, citations, or
UUIDs.
