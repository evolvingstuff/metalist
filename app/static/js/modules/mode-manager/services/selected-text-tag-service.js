export const MAX_SELECTED_TEXT_TAG_CHARACTERS = 25;

const TAG_CONTAINS_DISALLOWED = new Set([
    ':',
    ',',
    '"',
    '\\',
    '>',
    '<',
    '=',
    '[',
    ']',
    '{',
    '}',
    '(',
    ')',
    '*',
    '|',
    ';',
    '~',
    '`',
]);
const TOKEN_START_DISALLOWED = new Set(['-', '+', '/']);

function buildDefaultTagCandidate(normalizedSelectedText) {
    const spacesJoined = normalizedSelectedText.replace(/\s+/g, '-');
    let candidate = '';
    for (const char of spacesJoined) {
        const codePoint = char.codePointAt(0);
        if (!Number.isInteger(codePoint)) {
            throw new Error('Selected-text tag character missing code point');
        }
        if (codePoint < 0x20 || codePoint > 0x7e) {
            continue;
        }
        if (TAG_CONTAINS_DISALLOWED.has(char)) {
            continue;
        }
        candidate += char;
    }
    while (candidate.length > 0 && TOKEN_START_DISALLOWED.has(candidate[0])) {
        candidate = candidate.slice(1);
    }
    return candidate;
}

export function normalizeSelectedTextForTagAction(selectedText) {
    if (typeof selectedText !== 'string') {
        throw new Error('normalizeSelectedTextForTagAction expects selectedText string');
    }
    if (selectedText.length === 0 || selectedText.length > MAX_SELECTED_TEXT_TAG_CHARACTERS) {
        return null;
    }

    const normalizedSelectedText = selectedText.replace(/\s+/g, ' ').trim();
    if (normalizedSelectedText.length === 0) {
        return null;
    }
    if (buildDefaultTagCandidate(normalizedSelectedText).length === 0) {
        return null;
    }
    return normalizedSelectedText;
}
