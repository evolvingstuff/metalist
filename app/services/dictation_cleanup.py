"""Turn dictated text pasted into the search bar or the tag bar into tags.

Speech-to-text tools such as Superwhisper paste sentences ("Neural network,
neural network. Neural-Dash Network.") where the user meant tags
(`neural-network`). This module applies fixed rules, no AI; the behavior is
described case by case in docs/ui/dictation-paste.md:

- sentence punctuation is dropped; spoken joiners ("dash", "hyphen",
  "underscore", "slash", including Superwhisper's "foo-Dash bar") join words;
- "quote … end quote" (or quote marks) marks a phrase;
- the longest run of words matching an existing tag becomes that tag, matched
  ignoring case and treating space - _ . / alike, spelled as used most often;
  words also match a tag written as one word ("to do" -> `todo`), joiners first;
- "at" (or a typed @) before words naming a built-in meta tag is that meta tag
  ("at to do" -> `@todo`); otherwise "at" is filler;
- filler words are dropped unless they are tags; repeats and tags already in
  the field are not added again;
- search: unknown words are dropped, "or" becomes OR and "not"/"minus" exclude
  the next tag; tag bar: unknown words become new tags.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import re

from app.config import TAG_SUGGESTION_CONNECTORS


FILLER_WORDS = frozenset({"a", "an", "and", "at", "the", "tag", "tags", "comma", "period", "um", "uh"})
# The built-in meta tags (KNOWN_META_TAGS in tag-syntax-service.js; a unit test
# keeps the two lists equal).
KNOWN_META_TAGS = (
    "@footnote", "@monospace", "@heading", "@red", "@green", "@blue", "@grey",
    "@highlighter", "@bold", "@italic", "@strikethrough", "@serif", "@copyable",
    "@list-bulleted", "@list-numbered", "@username", "@password", "@email",
    "@todo", "@done", "@markdown", "@llm", "@latex", "@shell", "@json", "@csv",
)
_META_AT_WORDS = frozenset({"at", "@"})
# Meta tag names are at most this many words when spoken ("list bulleted").
_MAX_META_WORDS = 3
_SEARCH_OR_WORDS = frozenset({"or"})
_SEARCH_NOT_WORDS = frozenset({"not", "minus"})
_SPOKEN_JOINERS = {"dash": "-", "hyphen": "-", "underscore": "_", "slash": "/"}
_SENTENCE_PUNCTUATION = ",.?!;:"
_TAG_DISALLOWED = frozenset(':,"\\><=[]{}()*|;~`')
_TAG_START_DISALLOWED = frozenset("-+/")

# "foo-Dash bar", "foo - Dash bar", "foo dash bar": a spoken joiner between two
# words, with or without the symbol Superwhisper also types before it.
_SPOKEN_JOINER_RE = re.compile(
    r"(?<=\S)\s*[-_/]?\s*(?<![A-Za-z0-9])(" + "|".join(_SPOKEN_JOINERS) + r")(?![A-Za-z0-9])[\s,.]*(?=\S)",
    re.IGNORECASE,
)
_CURLY_QUOTES = str.maketrans({"“": '"', "”": '"', "„": '"'})
# A quoted phrase: quote marks, or the spoken "quote … end quote/unquote/close
# quote" (to the end of the text when it is never closed).
_QUOTED_RE = re.compile(
    r'"([^"]*)"|\bquote\b[\s,.:]*(.*?)[\s,.]*(?:\bend\s+quote\b|\bunquote\b|\bclose\s+quote\b|$)',
    re.IGNORECASE | re.DOTALL,
)
_EQUIVALENCE_SEPARATOR_RE = re.compile(f"[{re.escape(TAG_SUGGESTION_CONNECTORS)}\\s]+")
_NOT_LETTER_OR_DIGIT_RE = re.compile(r"[^0-9a-z]+")


@dataclass(frozen=True)
class _TagIndex:
    """Existing tags by equivalence key, and by their letters and digits only."""
    by_key: dict[str, str]
    by_compact_key: dict[str, str]


@dataclass(frozen=True)
class _Word:
    text: str


@dataclass(frozen=True)
class _Phrase:
    text: str


@dataclass(frozen=True)
class _Syntax:
    """Search syntax the user pasted as is (-tag, +tag, OR)."""
    text: str


def clean_dictated_paste(
    *,
    text: str,
    target: str,
    existing_tag_frequencies: Mapping[str, int],
    current_value: str,
) -> str:
    """The text to insert for a paste into the search bar (`search`) or tag bar (`tags`)."""
    if target not in {"search", "tags"}:
        raise ValueError(f"Unknown dictation paste target: {target!r}")
    if not isinstance(text, str) or not isinstance(current_value, str):
        raise TypeError("text and current_value must be strings")
    tag_index = _TagIndex(
        by_key=_most_used_spelling(existing_tag_frequencies, _equivalence_key),
        by_compact_key=_most_used_spelling(existing_tag_frequencies, _compact_key),
    )
    items = _items(text, target=target)
    if target == "search":
        return _search_text(items, tag_index=tag_index, current_value=current_value)
    return _tag_bar_text(items, tag_index=tag_index, current_value=current_value)


def _equivalence_key(text: str) -> str:
    return _EQUIVALENCE_SEPARATOR_RE.sub(" ", text.casefold()).strip()


def _compact_key(text: str) -> str:
    """Letters and digits only: "to do", "to-do" and "todo" are all "todo"."""
    return _NOT_LETTER_OR_DIGIT_RE.sub("", text.casefold())


_META_TAGS_BY_COMPACT_KEY = {_compact_key(tag): tag for tag in KNOWN_META_TAGS}
assert len(_META_TAGS_BY_COMPACT_KEY) == len(KNOWN_META_TAGS)


def _most_used_spelling(existing_tag_frequencies: Mapping[str, int], key_of) -> dict[str, str]:
    """Key -> the existing spelling used most often."""
    best: dict[str, tuple[str, int]] = {}
    for tag, frequency in existing_tag_frequencies.items():
        if not isinstance(tag, str) or tag == "":
            raise TypeError("existing tag names must be non-empty strings")
        if not isinstance(frequency, int) or frequency < 0:
            raise TypeError("existing tag frequencies must be non-negative integers")
        key = key_of(tag)
        if key == "":
            continue
        if key not in best:
            best[key] = (tag, frequency)
            continue
        kept_tag, kept_frequency = best[key]
        if (-frequency, tag.casefold(), tag) < (-kept_frequency, kept_tag.casefold(), kept_tag):
            best[key] = (tag, frequency)
    return {key: tag for key, (tag, _frequency) in best.items()}


def _join_spoken_joiners(text: str) -> str:
    return _SPOKEN_JOINER_RE.sub(lambda match: _SPOKEN_JOINERS[match.group(1).casefold()], text)


def _items(text: str, *, target: str) -> list[_Word | _Phrase | _Syntax]:
    """Words, quoted phrases and pasted search syntax, in order."""
    text = _join_spoken_joiners(text.translate(_CURLY_QUOTES))
    items: list[_Word | _Phrase | _Syntax] = []
    position = 0
    for match in _QUOTED_RE.finditer(text):
        items.extend(_words(text[position:match.start()], target=target))
        phrase = match.group(1)
        if phrase is None:
            phrase = match.group(2)
        phrase = " ".join(phrase.strip(_SENTENCE_PUNCTUATION + " ").split())
        if phrase:
            items.append(_Phrase(phrase))
        position = match.end()
    items.extend(_words(text[position:], target=target))
    return items


def _words(chunk: str, *, target: str) -> list[_Word | _Syntax]:
    words: list[_Word | _Syntax] = []
    for token in chunk.split():
        if target == "search" and (token == "OR" or (len(token) > 1 and token[0] in "-+" and token[1].isalnum())):
            words.append(_Syntax(token.rstrip(_SENTENCE_PUNCTUATION)))
            continue
        word = token.strip(_SENTENCE_PUNCTUATION)
        if word:
            words.append(_Word(word))
    return words


def _word_run_end(items: list, start: int) -> int:
    end = start
    while end < len(items) and isinstance(items[end], _Word):
        end += 1
    return end


def _match_at(items: list, start: int, tag_index: _TagIndex) -> tuple[str, int] | None:
    """The existing tag spelled by the longest run of words from `start`, and its
    length; at each length, a match keeping the joiners wins over one without."""
    for end in range(_word_run_end(items, start), start, -1):
        spoken = " ".join(item.text for item in items[start:end])
        key = _equivalence_key(spoken)
        if key in tag_index.by_key:
            return tag_index.by_key[key], end - start
        compact = _compact_key(spoken)
        if compact in tag_index.by_compact_key:
            return tag_index.by_compact_key[compact], end - start
    return None


def _meta_tag_at(items: list, start: int) -> tuple[str, int] | None:
    """"at to do" / "@ to do" / "@todo" -> ("@todo", words used); None otherwise."""
    word = items[start].text
    if word.casefold() in _META_AT_WORDS:
        first, named_from = [], start + 1
    elif word.startswith("@") and len(word) > 1:
        first, named_from = [word[1:]], start + 1
    else:
        return None
    run_end = min(_word_run_end(items, named_from), named_from + _MAX_META_WORDS)
    for end in range(run_end, named_from - 1, -1):
        compact = _compact_key("".join(first + [item.text for item in items[named_from:end]]))
        if compact in _META_TAGS_BY_COMPACT_KEY:
            return _META_TAGS_BY_COMPACT_KEY[compact], end - start
    return None


def _new_tag(text: str) -> str:
    """A new tag from dictated words: joined with dashes, lowercased unless an acronym."""
    words = []
    for word in text.split():
        letters = [char for char in word if char.isalpha()]
        if len(letters) >= 2 and all(char.isupper() for char in letters):
            words.append(word)
        else:
            words.append(word.lower())
    candidate = "".join(
        char for char in "-".join(words) if 0x20 < ord(char) <= 0x7E and char not in _TAG_DISALLOWED
    )
    candidate = candidate.lstrip("".join(_TAG_START_DISALLOWED))
    if candidate == "OR":
        return ""
    return candidate


def _quoted_search_text(phrase: str) -> str:
    return '"' + phrase.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _search_text(items: list, *, tag_index: _TagIndex, current_value: str) -> str:
    # Elements: a term, "OR", "NOT" (exclude the next term) or "DROP" (an
    # unknown word, which also cancels a pending NOT).
    elements: list[str] = []
    index = 0
    while index < len(items):
        item = items[index]
        if isinstance(item, _Syntax):
            elements.append(item.text)
            index += 1
            continue
        if isinstance(item, _Phrase):
            elements.append(_quoted_search_text(item.text))
            index += 1
            continue
        match = _meta_tag_at(items, index)
        if match is None:
            match = _match_at(items, index, tag_index)
        if match is not None:
            elements.append(match[0])
            index += match[1]
            continue
        word = item.text.casefold()
        if word in _SEARCH_OR_WORDS:
            elements.append("OR")
        elif word in _SEARCH_NOT_WORDS:
            elements.append("NOT")
        elif word not in FILLER_WORDS:
            elements.append("DROP")
        index += 1
    present = {term.casefold() for term in current_value.split()}
    clauses: list[list[str]] = [[]]
    pending_not = False
    for element in elements:
        if element == "OR":
            pending_not = False
            clauses.append([])
            continue
        if element == "NOT":
            pending_not = True
            continue
        if element == "DROP":
            pending_not = False
            continue
        term = element
        if pending_not:
            term = "-" + element
            pending_not = False
        if term.casefold() in present:
            continue
        present.add(term.casefold())
        clauses[-1].append(term)
    return " OR ".join(" ".join(clause) for clause in clauses if clause)


def _tag_bar_text(items: list, *, tag_index: _TagIndex, current_value: str) -> str:
    tags: list[str] = []
    present = {_equivalence_key(tag) for tag in current_value.split()}
    index = 0
    while index < len(items):
        item = items[index]
        if isinstance(item, _Phrase):
            tag = _new_tag(item.text)
            if _equivalence_key(item.text) in tag_index.by_key:
                tag = tag_index.by_key[_equivalence_key(item.text)]
            elif _compact_key(item.text) in tag_index.by_compact_key:
                tag = tag_index.by_compact_key[_compact_key(item.text)]
            index += 1
        else:
            match = _meta_tag_at(items, index)
            if match is None:
                match = _match_at(items, index, tag_index)
            if match is not None:
                tag = match[0]
                index += match[1]
            else:
                index += 1
                word = item.text.casefold()
                if word in FILLER_WORDS or word in _SEARCH_OR_WORDS or word in _SEARCH_NOT_WORDS:
                    continue
                tag = _new_tag(item.text)
        if tag == "" or _equivalence_key(tag) in present:
            continue
        present.add(_equivalence_key(tag))
        tags.append(tag)
    return " ".join(tags)
