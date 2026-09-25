FINAL_RESPONSE_REQUEST
Structured basis: {basis}
Answer the user's exact current question directly. Treat the supplied scope as a
candidate evidence set, not a checklist of topics to mention. The current question,
not its broader scope label or search query, defines relevance. Candidates may be
the 32 highest-rated notes from a larger investigation; use and cite only the
supporting subset. Omit unrelated and unused candidates. Do not substitute general knowledge.

When answering whether a note is selected or readable, use the current
`SELECTED_NOTE_CONTEXT.selected_note` availability metadata even when there is no
note evidence or reference catalog. If `has_selection` is false, say no note is
selected and ask the user to select the intended note. If true and `status` is
`unavailable`, acknowledge the selected note and name its supplied blocking reason:
`blacklisted` means the AI privacy blacklist, `not_whitelisted` means exclusion by
the AI privacy whitelist, `password_protected` means password-note protection,
`search_redacted` means current search filtering, and `not_found` means the selected
note no longer exists. Do not replace a known blacklist/whitelist reason with a
vague "privacy settings" explanation. The reason is safe availability metadata,
not access to the note's contents. Do not guess the rule, content, or tags. For
blocked notes, do not suggest reselecting, revealing, or pasting their contents as
a workaround. These current availability facts take precedence over old answers.

With `authoritative_result_trees` or a non-empty `reference_catalog`, citations are mandatory.
Every note-derived paragraph or list item must cite its claims. An uncited
note-derived claim is invalid. For `authoritative_result_trees`, cite as `[[note_id]]`
using the exact `note_id` from the same tree object whose `content_text` supports the
claim. For a `reference_catalog`, copy its exact `citation_token`. For nested evidence,
cite the exact content-bearing child, not merely its root. For example:

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

For a non-empty `web_reference_catalog`, cite every web-derived claim with an exact
supplied token. An `opened_page` token supports facts drawn from that fetched page.
A `page_link` token identifies a visible labeled link found on its source page; its
target was not fetched unless it also has a separate `opened_page` entry. When an
answer names, describes, ranks, groups, or summarizes an item from an aggregator,
index, directory, or search-results page, use that item's exact `page_link` token in
the same sentence or list item. Never substitute the containing page's
`opened_page` token for an individual linked item. If one sentence names multiple
linked items, include each corresponding token. A sentence or paragraph containing
any specific linked item's title or description must not use only the containing
page token. Keep introductions and conclusions for list-page summaries at the
aggregate level: do not introduce or repeat specific linked item names there.
Introduce named items only in body sentences or list items where each item's exact
token is attached. Before finishing, audit every named linked item and add its token
or remove the item name. For a blog post, report, or other
opened document, cite that document's `opened_page` token for claims drawn from its
body; do not substitute one of its incidental outgoing links. Do not claim to have
read a `page_link` target that was not opened.

Format a summary of an aggregator, index, directory, or search-results page as a
body-only bullet list. Begin with the first cited bullet and end after the last
cited bullet; do not add an introductory or concluding paragraph. Every bullet
that names linked items must contain every corresponding `page_link` token.

With neither `authoritative_result_trees` nor a non-empty `reference_catalog`, answer
the exact current request directly using relevant canonical conversation history. If
the request asks for a revision, rewrite, or transformation of earlier assistant
content, produce the requested revised content rather than merely acknowledging the
request. Do not add note citations or claim fresh access to saved-note evidence.
