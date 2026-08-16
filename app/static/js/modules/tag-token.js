const DISALLOWED_TAG_CHARS = new Set([
    ':',
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

export function isValidTagToken(token) {
    if (typeof token !== 'string') {
        throw new Error('isValidTagToken requires string');
    }
    if (token.trim() !== token) {
        return false;
    }
    if (token.length === 0) {
        return false;
    }
    if (token === 'OR') {
        return false;
    }
    if (/\s/.test(token)) {
        return false;
    }
    if (token.startsWith('-') || token.startsWith('+') || token.startsWith('/')) {
        return false;
    }
    if (token.startsWith('"') || token.startsWith("'")) {
        return false;
    }
    if (token.startsWith('(') || token.startsWith(')')) {
        return false;
    }
    for (const ch of token) {
        if (DISALLOWED_TAG_CHARS.has(ch)) {
            return false;
        }
    }
    return true;
}
