# Dictation (speech to text)

Use this reference to explain MetaList accurately. It describes user capabilities,
not permission or tools for you to execute every operation. You can answer and
request one supported menu/dialog opening. You cannot submit a form, change
settings, run a shell command, or mutate notes through this help response. Do not
claim that you inspected current notes or settings: none are supplied here.
Prefer user-facing steps over implementation details. If the reference does not
answer a question, say what is unknown; do not invent syntax or controls.

Sources: docs/ui/dictation-paste.md

## What it is for

Speech-to-text tools such as Superwhisper paste sentences, not tags: saying
"neural network" can arrive as `Neural network, neural network. Neural-Dash
Network.` MetaList cleans up such text when it is **pasted** into the search bar, a
note's tag bar, or a note being edited, and turns it into the user's tags. It uses
fixed rules, no AI, and it only reacts to pasting: typed text is never changed.

## How dictated words become tags

- Sentence punctuation (`, . ? ! ; :`) is dropped.
- Spoken joiners join words: "dash" or "hyphen" gives `-`, "underscore" `_`,
  "slash" `/`. Superwhisper's `foo-Dash bar` gives `foo-bar`.
- The longest run of words matching one of the user's existing tags becomes that
  tag, ignoring capitals and treating spaces, `-`, `_`, `.` and `/` alike, spelled
  the way the user uses it most. "neural network" gives `neural-network`.
- Words also match a tag written as one word: "to do" gives `todo`, "scratch pad"
  gives `scratchpad`.
- "at" before the name of a built-in meta tag gives that meta tag: "at to do" gives
  `@todo`, "at done" `@done`, "at list bulleted" `@list-bulleted`. Otherwise "at"
  is ignored.
- "quote … end quote" (also "unquote") marks a phrase.
- Filler words (a, an, and, at, the, tag, tags, comma, period, um, uh) are ignored,
  unless the word is itself one of the user's tags. A spoken word that is a tag
  always stays that tag.
- Repeats count once, and tags already in the field are not added again.

## Where to paste

- **Search bar:** words matching no tag are dropped. "or" becomes `OR`, "not" and
  "minus" exclude the next tag ("neural network not python" gives
  `neural-network -python`), and a quoted phrase becomes a text search.
- **Tag bar:** words matching no tag become new tags, lowercased unless they look
  like an acronym (`GPT`). A quoted phrase becomes one tag: "quote machine learning
  end quote" gives `machine-learning`.
- **A note being edited:** say the tag phrase, **"start tags"** by default, then the
  tags. The text before the phrase goes into the note; the words after it are added
  to the note's tags with the tag-bar rules. "Here is my content. Start tags. Neural
  network, at to do." adds the content and the tags `neural-network @todo`. Saying
  only "Start tags, scratch pad." adds just the tag. Only the first phrase counts.
  Without the phrase, a paste into a note is an ordinary paste.

It is a phrase rather than a repeated word because Superwhisper drops a word said
twice in a row.

## Undo

One undo (Cmd/Ctrl+Z) right after the paste brings back what was pasted in the
search bar or tag bar (in the tag bar without commas, which tags cannot contain).
After a paste into a note, one undo removes both the pasted text and the added tags.

## Setting the tag phrase

The command palette's **Dictation Settings** dialog sets the phrase that starts tags
in a note. It must be words of letters, 2 to 64 characters: "start tags", "now add
these tags", or one unusual word such as "armadillo". Save applies it.

## Tips and limits

- Plurals do not match: "transformers" is not the tag `transformer`. In search it
  is dropped; in the tag bar it becomes a new tag.
- A new multi-word tag needs quoting ("quote scratch pad end quote" gives
  `scratch-pad`); without quotes the words become separate tags.
- Saying "dash" in its ordinary sense ("100 meter dash") joins the words around it.
- `@size=…` and other values cannot be dictated; type them.
