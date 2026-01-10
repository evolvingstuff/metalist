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

    let out = '';
    for (const char of token) {
        if (!isAsciiPrintable(char)) {
            continue;
        }
        if (TAG_CONTAINS_DISALLOWED.has(char)) {
            continue;
        }
        out += char;
    }
    return out;
}

function enforceTagBarInputInternal(rawInput, options) {
    if (typeof rawInput !== 'string') {
        throw new Error('enforceTagBarInputInternal expects a string');
    }

    const allowTrailingCommentStart = Boolean(options && options.allowTrailingCommentStart);

    let output = '';
    let currentToken = '';
    let inComment = false;

    const flushToken = ({ isFinal }) => {
        if (currentToken.length === 0) {
            return;
        }

        if (allowTrailingCommentStart && isFinal && currentToken === '/') {
            output += currentToken;
        } else {
            output += enforceTagToken(currentToken);
        }
        currentToken = '';
    };

    for (let index = 0; index < rawInput.length; index += 1) {
        const char = rawInput[index];
        const nextChar = index + 1 < rawInput.length ? rawInput[index + 1] : '';

        if (!inComment && char === '/' && nextChar === '*') {
            flushToken({ isFinal: false });
            output += '/*';
            inComment = true;
            index += 1;
            continue;
        }

        if (inComment) {
            if (char === '*' && nextChar === '/') {
                output += '*/';
                inComment = false;
                index += 1;
                continue;
            }
            if (!isAsciiPrintable(char)) {
                continue;
            }
            output += char;
            continue;
        }

        if (isWhitespace(char)) {
            flushToken({ isFinal: false });
            if (output.length > 0 && output[output.length - 1] !== ' ') {
                output += ' ';
            }
            continue;
        }

        currentToken += char;
    }

    flushToken({ isFinal: true });
    return output;
}

export function enforceTagBarInput(rawInput) {
    return enforceTagBarInputInternal(rawInput, { allowTrailingCommentStart: false });
}

export function enforceTagBarInputForEditing(rawInput) {
    return enforceTagBarInputInternal(rawInput, { allowTrailingCommentStart: true });
}

function scanTagBarSegments(rawInput) {
    if (typeof rawInput !== 'string') {
        throw new Error('scanTagBarSegments expects a string');
    }

    const segments = [];
    let currentToken = '';
    let index = 0;
    while (index < rawInput.length) {
        if (rawInput.startsWith('/*', index)) {
            if (currentToken.length > 0) {
                segments.push({ type: 'token', text: currentToken });
                currentToken = '';
            }

            const closeIndex = rawInput.indexOf('*/', index + 2);
            if (closeIndex === -1) {
                return { segments, unclosedCommentText: rawInput.slice(index) };
            }

            segments.push({ type: 'comment', text: rawInput.slice(index, closeIndex + 2) });
            index = closeIndex + 2;
            continue;
        }

        const char = rawInput[index];
        if (isWhitespace(char)) {
            if (currentToken.length > 0) {
                segments.push({ type: 'token', text: currentToken });
                currentToken = '';
            }
            index += 1;
            continue;
        }

        currentToken += char;
        index += 1;
    }

    if (currentToken.length > 0) {
        segments.push({ type: 'token', text: currentToken });
    }

    return { segments, unclosedCommentText: null };
}

export function analyzeTagBarInput(rawInput) {
    if (typeof rawInput !== 'string') {
        throw new Error('analyzeTagBarInput expects a string');
    }

    const enforcedText = enforceTagBarInput(rawInput);
    const { segments, unclosedCommentText } = scanTagBarSegments(enforcedText);


    const sanitizedSegments = segments.map((segment) => segment.text);
    const sanitizedText = sanitizedSegments.join(' ').trim();

    const normalizedSegments = [...sanitizedSegments];
    if (unclosedCommentText) {
        normalizedSegments.push(unclosedCommentText);
    }
    const normalizedText = normalizedSegments.join(' ').trim();

    const errorMessage = unclosedCommentText ? 'Close comment with */' : null;

    return {
        isValid: errorMessage === null,
        errorMessage,
        sanitizedText,
        normalizedText,
    };
}

export function normalizeTagBarInput(rawInput) {
    if (typeof rawInput !== 'string') {
        throw new Error('normalizeTagBarInput expects a string');
    }

    return analyzeTagBarInput(rawInput).normalizedText;
}
