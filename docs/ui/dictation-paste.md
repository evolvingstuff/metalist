# Dictation Paste

Speech-to-text tools such as Superwhisper paste sentences, not tags: saying
"neural network" can arrive as `Neural network, neural network. Neural-Dash
Network.` Pasting into the **search bar** or a note's **tag bar** turns such
text into the user's tags with fixed rules (no AI). Typing is never changed,
only pastes.

## Rules (both fields)

1. Sentence punctuation (`, . ? ! ; :`) is dropped.
2. Spoken joiners join words: "dash" and "hyphen" give `-`, "underscore" `_`,
   "slash" `/`. Superwhisper's `foo-Dash bar` (a typed `-` plus the word) and
   the variants `foo -Dash bar`, `foo - Dash bar`, `foo dash bar` all give `foo-bar`.
3. "quote … end quote" (also "unquote", "close quote") or quote marks, straight
   or curly, mark a phrase.
4. At each word, the longest run of words matching an existing tag becomes that
   tag. Matching ignores case and treats space, `-`, `_`, `.` and `/` alike (as
   Add as Tag does); the spelling used most often wins. `neural network` becomes
   `neural-network`, not `neural` and `network`, even when those exist too.
5. Repeats collapse to one, and tags already in the field are not added again.
6. Filler words (`a`, `an`, `and`, `the`, `tag`, `tags`, `comma`, `period`, `um`,
   `uh`) are dropped, unless the word is itself one of the user's tags.
7. The result replaces the selection, with spaces so it never runs into the tags
   around it. One undo brings back what was pasted (in the tag bar without commas,
   which tags cannot contain).

## Search bar and tag bar

| Situation | Search bar | Tag bar |
|---|---|---|
| Word or phrase matching an existing tag | the tag | the tag |
| Unknown word | dropped | a new tag, lowercased unless it looks like an acronym (`GPT`, `LLM`) |
| Quoted phrase | a text search, `"attention is all you need"` | one tag, `machine-learning` (or the existing tag it matches) |
| "or" | `OR` between clauses | dropped |
| "not", "minus" | exclude the next tag, `-python` | dropped |
| Pasted search syntax (`-tag`, `+tag`, `OR`, `"text"`) | kept as is | not applicable |

A spoken word that is one of the user's tags is always that tag: with a tag
`not`, "not python" is `not python`. An operator with nothing to apply to (a
leading or trailing "or", "not" before an unknown word) is dropped.

## Implementation

- Server: `app/services/dictation_cleanup.py` `clean_dictated_paste()`, against
  `search_index.list_explicit_tag_frequencies()`; read-only endpoint
  `POST /api2/notes/dictation-paste` `{text, target: "search"|"tags", current_value}`.
- Browser: `dictation-paste-service.js` handles `paste` on `#search-input` and on
  `.note-tag-bar-input`. It inserts the pasted text as is, then replaces it with
  the cleaned text, both as native edits, so the field's own undo restores the
  paste; input handlers skip the as-is step (`isDictationRawInsertInProgress()`).
- Tests: `tests/unit/test_dictation_cleanup.py` (every case above),
  `tests/unit/dictation_paste_padding.test.mjs`, and the browser suite
  `BROWSER_TEST_SUITE=dictation-paste npm run test:browser`.
