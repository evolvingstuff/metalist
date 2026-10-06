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
   Words also match a tag written as one word: "to do" becomes `todo`, "super
   whisper" `superwhisper`. At the same length, a match keeping the joiners wins
   (with both `to-do` and `todo`, "to do" is `to-do`).
5. "at" (or a typed `@`) before words naming a built-in meta tag is that meta tag:
   "at to do", "At todo.", "@ to do" and `@todo` all give `@todo`; "at list
   bulleted" gives `@list-bulleted`. The built-in list is `KNOWN_META_TAGS` in
   `tag-syntax-service.js`, mirrored in `dictation_cleanup.py` (a test keeps them
   equal). `@size=…` is keyboard only.
6. Repeats collapse to one, and tags already in the field are not added again.
7. Filler words (`a`, `an`, `and`, `at`, `the`, `tag`, `tags`, `comma`, `period`,
   `um`, `uh`) are dropped, unless the word is itself one of the user's tags (or,
   for `at`, it starts a meta tag).
8. The result replaces the selection, with spaces so it never runs into the tags
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

## Dictating Tags into a Note

When dictated text is pasted into the note being edited, a tag phrase starts the
tags. It is `start tags` by default, set in the command palette's **Dictation
Settings** (`pref.dictation.tag_phrase`: words of letters, 2 to 64 characters; one
unusual word such as `armadillo` is enough). It is a phrase rather than a word said
twice because dictation tools such as Superwhisper drop a repeated word.

- The phrase's words match as whole words, in any capitalization, with spaces or
  punctuation between them: `start tags`, `Start tags.`, `start, tags:`.
- The text before it is inserted at the caret as plain text. A comma or space right
  before the phrase is dropped; a sentence's closing `.`, `?` or `!` stays.
- The words after it are added to the note's tag bar with the tag-bar rules above
  (existing tags matched, unknown words become new tags, tags already there skipped).
- Only the first phrase counts; later ones are dropped from the tags.
- Without the phrase the paste is unchanged.
- One undo right after the paste removes both the pasted text and the added tags (if
  only tags were dictated, it removes just the tags). Any other edit in between ends
  this pairing; undo then works as usual.

| Pasted into a note | Note text gets | Tags get |
|---|---|---|
| `Here is my content start tags foo bar` | `Here is my content` | `foo bar` |
| `Here is my content. Start tags. Neural network, python.` | `Here is my content.` | `neural-network python` |
| `Start tags neural network at to do` | nothing | `neural-network @todo` |
| `Here is my content start tags` | `Here is my content` | nothing |
| `The paper about neural networks` | unchanged paste | nothing |

## Implementation

- Server: `app/services/dictation_cleanup.py` `clean_dictated_paste()`, against
  `search_index.list_explicit_tag_frequencies()`; read-only endpoint
  `POST /api2/notes/dictation-paste` `{text, target: "search"|"tags", current_value}`.
- Browser: `dictation-paste-service.js` handles `paste` on `#search-input` and on
  `.note-tag-bar-input`. It inserts the pasted text as is, then replaces it with
  the cleaned text, both as native edits, so the field's own undo restores the
  paste; input handlers skip the as-is step (`isDictationRawInsertInProgress()`).
- Note pastes: `dictation-note-paste.js` splits at the tag phrase (pure);
  `handleDictatedNotePaste()` in `dictation-paste-service.js` inserts the text as one
  native edit and adds the cleaned tags; `undoDictatedNotePasteTags()` runs from the
  undo shortcut and puts the tag bar back. The keyword reaches it from the command
  palette's preference effects (`receiveDictationTagPhrase`).
- In-app help: the `dictation` help topic (`app/services/agent/skills/help-dictation.md`);
  live evals `evals/agent-cases/help/*dictation*.json`.
- Tests: `tests/unit/test_dictation_cleanup.py` (every case above),
  `tests/unit/dictation_note_paste.test.mjs` (the tag phrase),
  `tests/unit/dictation_paste_padding.test.mjs`, and the browser suite
  `BROWSER_TEST_SUITE=dictation-paste npm run test:browser`.
