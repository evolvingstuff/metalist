const TAG_CONTAINS_DISALLOWED = new Set([
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

const TOKEN_START_DISALLOWED = new Set(['-', '+', '/']);

const QUOTE_CHARS = new Set(['"', "'" ]);

function isAsciiPrintable(char) {
    if (typeof char !== 'string' || char.length === 0) {
        return false;
    }
    const code = char.charCodeAt(0);
    return code >= 0x20 && code <= 0x7e;
}

function isWhitespace(char) {
    return typeof char === 'string' && char.length === 1 && /\s/.test(char);
}

function enforceTagToken(rawToken) {
    if (typeof rawToken !== 'string') {
        throw new Error('enforceTagToken expects a string');
    }

    let token = rawToken;
    while (token.length > 0 && TOKEN_START_DISALLOWED.has(token[0])) {
        token = token.slice(1);
    }

    let output = '';
    for (const char of token) {
        if (!isAsciiPrintable(char)) {
            continue;
        }
        if (TAG_CONTAINS_DISALLOWED.has(char)) {
            continue;
        }
        output += char;
    }

    return output;
}

function readQuotedInner(rawInput, startIndex, quoteChar) {
    if (typeof rawInput !== 'string') {
        throw new Error('readQuotedInner expects rawInput string');
    }
    if (!Number.isInteger(startIndex) || startIndex < 0) {
        throw new Error('readQuotedInner expects startIndex integer');
    }
    if (quoteChar !== '"' && quoteChar !== "'") {
        throw new Error('readQuotedInner expects quoteChar to be " or \'');
    }

    let index = startIndex;
    let normalizedInner = '';
    let closed = false;

    while (index < rawInput.length) {
        const char = rawInput[index];

        if (char === quoteChar) {
            closed = true;
            index += 1;
            break;
        }

        if (char === '\\') {
            if (index + 1 < rawInput.length) {
                const nextChar = rawInput[index + 1];
                if (nextChar === quoteChar || nextChar === '\\') {
                    normalizedInner += `\\${nextChar}`;
                    index += 2;
                    continue;
                }
            }

            if (isAsciiPrintable(char)) {
                normalizedInner += char;
            }
            index += 1;
            continue;
        }

        if (isAsciiPrintable(char)) {
            normalizedInner += char;
        }
        index += 1;
    }

    return { normalizedInner, closed, nextIndex: index };
}

export function analyzeSearchQueryInput(rawInput) {
    if (typeof rawInput !== 'string') {
        throw new Error('analyzeSearchQueryInput expects a string');
    }

    const normalizedTerms = [];
    const sanitizedTerms = [];

    const hasTrailingWhitespace = rawInput.length > 0 && isWhitespace(rawInput[rawInput.length - 1]);

    let isComplete = true;
    let warningMessage = null;

    let index = 0;
    while (index < rawInput.length) {
        while (index < rawInput.length && isWhitespace(rawInput[index])) {
            index += 1;
        }
        if (index >= rawInput.length) {
            break;
        }

        let prefix = null;
        const firstChar = rawInput[index];
        if (firstChar === '+' || firstChar === '-') {
            prefix = firstChar;
            index += 1;
            if (index >= rawInput.length || isWhitespace(rawInput[index])) {
                normalizedTerms.push(prefix);
                isComplete = false;
                continue;
            }
        }

        const nextChar = rawInput[index];
        const isQuoteStart = QUOTE_CHARS.has(nextChar);
        if (isQuoteStart && prefix === '+') {
            // `+` is a tag-term modifier only. Drop it for quoted text.
            prefix = null;
        }

        if (isQuoteStart && (prefix === null || prefix === '-')) {
            const quoteChar = nextChar;
            index += 1;
            const { normalizedInner, closed, nextIndex } = readQuotedInner(rawInput, index, quoteChar);
            index = nextIndex;

            const prefixText = prefix === null ? '' : prefix;
            const normalized = `${prefixText}${quoteChar}${normalizedInner}`;

            if (!closed) {
                normalizedTerms.push(normalized);
                isComplete = false;
                if (!warningMessage && normalizedInner.length > 0) {
                    warningMessage = `Close quote with ${quoteChar}`;
                }
                continue;
            }

            const closedToken = `${normalized}${quoteChar}`;
            normalizedTerms.push(closedToken);

            if (normalizedInner.length === 0) {
                isComplete = false;
                if (!warningMessage) {
                    warningMessage = 'Enter text inside quotes';
                }
                continue;
            }

            sanitizedTerms.push(closedToken);
            continue;
        }

        let rawToken = '';
        while (index < rawInput.length && !isWhitespace(rawInput[index])) {
            rawToken += rawInput[index];
            index += 1;
        }

        const enforcedToken = enforceTagToken(rawToken);
        if (enforcedToken.length === 0) {
            if (prefix) {
                normalizedTerms.push(prefix);
                isComplete = false;
            }
            continue;
        }

        const prefixText = prefix === null ? '' : prefix;
        const normalizedTag = `${prefixText}${enforcedToken}`;
        normalizedTerms.push(normalizedTag);
        sanitizedTerms.push(normalizedTag);
    }

    const normalizedText = normalizedTerms.join(' ').trim();
    const sanitizedText = sanitizedTerms.join(' ').trim();

    const enforcedText = hasTrailingWhitespace && normalizedText.length > 0
        ? `${normalizedText} `
        : normalizedText;

    return {
        normalizedText,
        enforcedText,
        sanitizedText,
        isComplete,
        warningMessage,
    };
}

export function enforceSearchQueryInputForEditing(rawInput) {
    return analyzeSearchQueryInput(rawInput).enforcedText;
}

export function normalizeSearchQueryInput(rawInput) {
    return analyzeSearchQueryInput(rawInput).normalizedText;
}
