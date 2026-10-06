// Dictated text pasted into a note can end with tags: everything after the tag
// phrase ("start tags" by default, configurable in Dictation settings) becomes
// tags (docs/ui/dictation-paste.md). A phrase, not a word said twice: dictation
// tools such as Superwhisper drop a repeated word. Pure functions.

export const DEFAULT_DICTATION_TAG_PHRASE = 'start tags';
export const DICTATION_TAG_PHRASE_PREFERENCE = 'pref.dictation.tag_phrase';

// Words of letters separated by single spaces (one unusual word is enough).
export function isValidDictationTagPhrase(phrase) {
    return typeof phrase === 'string' && phrase.length >= 2 && phrase.length <= 64
        && /^[A-Za-z]+(?: [A-Za-z]+)*$/.test(phrase);
}

function phrasePattern(phrase, flags) {
    if (!isValidDictationTagPhrase(phrase)) {
        throw new Error(`Invalid dictation tag phrase: ${phrase}`);
    }
    // The phrase's words as whole words, with spaces or punctuation between them.
    const words = phrase.split(' ').join('[\\s,.;:!?]+');
    return new RegExp(`(?<![A-Za-z])${words}(?![A-Za-z])[\\s,.;:!?]*`, flags);
}

// { content, tagText } split at the first tag phrase, or null when there is none.
export function splitDictatedNotePaste(text, phrase) {
    if (typeof text !== 'string') {
        throw new TypeError('splitDictatedNotePaste requires text');
    }
    const match = phrasePattern(phrase, 'i').exec(text);
    if (match === null) {
        return null;
    }
    // A sentence's closing . ? ! stays with the content; a comma before the phrase does not.
    const content = text.slice(0, match.index).replace(/[\s,;:]+$/, '');
    const tagText = text.slice(match.index + match[0].length)
        .replace(phrasePattern(phrase, 'gi'), ' ')
        .replace(/\s+/g, ' ')
        .trim();
    return { content, tagText };
}
