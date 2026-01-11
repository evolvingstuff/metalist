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

const TAG_WRAPPER_OPENERS = new Set(['[', '{', '(']);
const TAG_WRAPPER_PAIRS = new Map([
    ['[', ']'],
    ['{', '}'],
    ['(', ')'],
]);
const TAG_WRAPPER_CHARS = new Set(['[', ']', '{', '}', '(', ')']);

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

function enforceWrappedTagTokenInternal(rawToken, preserveTrailingSpaceWhenUnclosed) {
    if (typeof rawToken !== 'string') {
        throw new Error('enforceWrappedTagToken expects a string');
    }
    if (typeof preserveTrailingSpaceWhenUnclosed !== 'boolean') {
        throw new Error('enforceWrappedTagTokenInternal expects preserveTrailingSpaceWhenUnclosed boolean');
    }

    if (rawToken.length === 0) {
        return '';
    }

    const opener = rawToken[0];
    if (!TAG_WRAPPER_OPENERS.has(opener)) {
        return enforceTagToken(rawToken);
    }

    const closer = TAG_WRAPPER_PAIRS.get(opener);
    if (typeof closer !== 'string') {
        throw new Error(`Unknown tag wrapper opener: ${opener}`);
    }

    let openerCount = 0;
    while (openerCount < rawToken.length && rawToken[openerCount] === opener && openerCount < 3) {
        openerCount += 1;
    }

    let remainder = rawToken.slice(openerCount);

    const remainderHadTrailingWhitespace = /\s$/.test(remainder);

    while (remainder.length > 0 && TAG_WRAPPER_CHARS.has(remainder[remainder.length - 1]) && remainder[remainder.length - 1] !== closer) {
        remainder = remainder.slice(0, -1);
    }

    let closerCount = 0;
    while (closerCount < openerCount && remainder.endsWith(closer)) {
        closerCount += 1;
        remainder = remainder.slice(0, -1);
    }

    const innerParts = remainder
        .split(/\s+/)
        .map((part) => enforceTagToken(part))
        .filter((part) => part.length > 0);
    let sanitizedInner = innerParts.join(' ');
    const wrapperIsUnclosed = closerCount < openerCount;
    if (preserveTrailingSpaceWhenUnclosed && wrapperIsUnclosed && remainderHadTrailingWhitespace && sanitizedInner.length > 0) {
        sanitizedInner += ' ';
    }
    if (sanitizedInner.length === 0) {
        if (openerCount > closerCount) {
            return opener.repeat(openerCount);
        }
        return '';
    }

    const prefix = opener.repeat(openerCount);
    const suffix = closer.repeat(closerCount);
    return `${prefix}${sanitizedInner}${suffix}`;
}

function enforceWrappedTagToken(rawToken) {
    return enforceWrappedTagTokenInternal(rawToken, false);
}

function enforceWrappedTagTokenForEditing(rawToken) {
    return enforceWrappedTagTokenInternal(rawToken, true);
}

function analyzeUnclosedWrapperTokenInfo(token) {
    if (typeof token !== 'string') {
        throw new Error('analyzeUnclosedWrapperTokenInfo expects a string');
    }

    if (token.length === 0) {
        return null;
    }

    const opener = token[0];
    if (!TAG_WRAPPER_OPENERS.has(opener)) {
        return null;
    }

    const closer = TAG_WRAPPER_PAIRS.get(opener);
    if (typeof closer !== 'string') {
        throw new Error(`Unknown tag wrapper opener: ${opener}`);
    }

    let openerCount = 0;
    while (openerCount < token.length && token[openerCount] === opener && openerCount < 3) {
        openerCount += 1;
    }

    let closerCount = 0;
    while (
        closerCount < token.length
        && token[token.length - 1 - closerCount] === closer
        && closerCount < openerCount
    ) {
        closerCount += 1;
    }

    if (closerCount >= openerCount) {
        return null;
    }

    const inner = token.slice(openerCount, token.length - closerCount);
    const innerParts = inner
        .split(/\s+/)
        .map((part) => enforceTagToken(part))
        .filter((part) => part.length > 0);
    const shouldWarn = innerParts.length > 0;

    return {
        missingSuffix: closer.repeat(openerCount - closerCount),
        shouldWarn,
    };
}

function enforceTagBarInputInternal(rawInput, options) {
    if (typeof rawInput !== 'string') {
        throw new Error('enforceTagBarInputInternal expects a string');
    }

    const allowTrailingCommentStart = Boolean(options && options.allowTrailingCommentStart);

    let output = '';
    let currentToken = '';
    let inComment = false;
    let wrapper = null;

    const flushToken = ({ isFinal }) => {
        if (currentToken.length === 0) {
            return;
        }

        if (allowTrailingCommentStart && currentToken === '/') {
            output += currentToken;
        } else {
            if (allowTrailingCommentStart) {
                output += enforceWrappedTagTokenForEditing(currentToken);
            } else {
                output += enforceWrappedTagToken(currentToken);
            }
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

        if (!wrapper && currentToken.length === 0 && TAG_WRAPPER_OPENERS.has(char)) {
            const opener = char;
            const closer = TAG_WRAPPER_PAIRS.get(opener);
            if (typeof closer !== 'string') {
                throw new Error(`Unknown tag wrapper opener: ${opener}`);
            }
            let openerCount = 0;
            while (openerCount < rawInput.length - index && rawInput[index + openerCount] === opener && openerCount < 3) {
                openerCount += 1;
            }
            wrapper = { opener, closer, openerCount };
            currentToken += opener.repeat(openerCount);
            index += openerCount - 1;
            continue;
        }

        if (isWhitespace(char) && !wrapper) {
            flushToken({ isFinal: false });
            if (output.length > 0 && output[output.length - 1] !== ' ') {
                output += ' ';
            }
            continue;
        }

        currentToken += char;

        if (wrapper && currentToken.endsWith(wrapper.closer.repeat(wrapper.openerCount))) {
            wrapper = null;
        }
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
    let wrapper = null;
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
        if (!wrapper && currentToken.length === 0 && TAG_WRAPPER_OPENERS.has(char)) {
            const opener = char;
            const closer = TAG_WRAPPER_PAIRS.get(opener);
            if (typeof closer !== 'string') {
                throw new Error(`Unknown tag wrapper opener: ${opener}`);
            }
            let openerCount = 0;
            while (openerCount < rawInput.length - index && rawInput[index + openerCount] === opener && openerCount < 3) {
                openerCount += 1;
            }
            wrapper = { opener, closer, openerCount };
            currentToken += opener.repeat(openerCount);
            index += openerCount;
            continue;
        }

        if (isWhitespace(char) && !wrapper) {
            if (currentToken.length > 0) {
                segments.push({ type: 'token', text: currentToken });
                currentToken = '';
            }
            index += 1;
            continue;
        }

        currentToken += char;
        index += 1;

        if (wrapper && currentToken.endsWith(wrapper.closer.repeat(wrapper.openerCount))) {
            wrapper = null;
        }
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


    let unclosedWrapperSuffix = null;

    const sanitizedSegments = [];
    const normalizedSegments = [];
    for (const segment of segments) {
        normalizedSegments.push(segment.text);
        if (segment.type === 'token') {
            const wrapperInfo = analyzeUnclosedWrapperTokenInfo(segment.text);
            if (wrapperInfo) {
                if (wrapperInfo.shouldWarn && !unclosedWrapperSuffix) {
                    unclosedWrapperSuffix = wrapperInfo.missingSuffix;
                }
                continue;
            }
        }
        sanitizedSegments.push(segment.text);
    }

    const sanitizedText = sanitizedSegments.join(' ').trim();

    if (unclosedCommentText) {
        normalizedSegments.push(unclosedCommentText);
    }
    const normalizedText = normalizedSegments.join(' ').trim();

    const shouldWarnUnclosedComment = Boolean(unclosedCommentText) && unclosedCommentText.length > 2;

    const errorMessage = shouldWarnUnclosedComment
        ? 'Close comment with */'
        : (unclosedWrapperSuffix ? `Close tag wrapper with ${unclosedWrapperSuffix}` : null);

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
