const WRAPPER_TYPES = Object.freeze([
    Object.freeze({ opener: '{', closer: '}' }),
    Object.freeze({ opener: '[', closer: ']' }),
    Object.freeze({ opener: '(', closer: ')' }),
]);

export const ADD_STYLE_OPTIONS = Object.freeze([
    Object.freeze({ id: 'heading', label: 'Heading', tag: '@heading' }),
    Object.freeze({ id: 'bold', label: 'Bold', tag: '@bold' }),
    Object.freeze({ id: 'italic', label: 'Italic', tag: '@italic' }),
    Object.freeze({ id: 'strikethrough', label: 'Strikethrough', tag: '@strikethrough' }),
    Object.freeze({ id: 'monospace', label: 'Monospace', tag: '@monospace' }),
    Object.freeze({ id: 'serif', label: 'Serif', tag: '@serif' }),
    Object.freeze({ id: 'red', label: 'Red', tag: '@red' }),
    Object.freeze({ id: 'green', label: 'Green', tag: '@green' }),
    Object.freeze({ id: 'blue', label: 'Blue', tag: '@blue' }),
    Object.freeze({ id: 'grey', label: 'Grey', tag: '@grey' }),
    Object.freeze({ id: 'copyable', label: 'Copyable', tag: '@copyable' }),
    Object.freeze({ id: 'markdown', label: 'Markdown', tag: '@markdown' }),
    Object.freeze({ id: 'latex', label: 'LaTeX', tag: '@LaTeX' }),
    Object.freeze({ id: 'json', label: 'JSON', tag: '@json' }),
    Object.freeze({ id: 'csv', label: 'CSV', tag: '@csv' }),
    Object.freeze({ id: 'shell', label: 'Shell', tag: '@shell' }),
]);

const KNOWN_STYLE_TAGS = new Set(ADD_STYLE_OPTIONS.map((option) => option.tag));

function requireText(value, name) {
    if (typeof value !== 'string') {
        throw new Error(`${name} must be a string`);
    }
}

function requireKnownStyleTag(styleTag) {
    requireText(styleTag, 'styleTag');
    if (!KNOWN_STYLE_TAGS.has(styleTag)) {
        throw new Error(`Unknown Add Style tag: ${styleTag}`);
    }
}

function scanTopLevelTagTokens(tagBarText) {
    requireText(tagBarText, 'tagBarText');

    const tokens = [];
    let index = 0;
    while (index < tagBarText.length) {
        while (index < tagBarText.length && /\s/.test(tagBarText[index])) {
            index += 1;
        }
        if (index >= tagBarText.length) {
            break;
        }
        if (tagBarText.startsWith('/*', index)) {
            const commentEnd = tagBarText.indexOf('*/', index + 2);
            if (commentEnd === -1) {
                break;
            }
            index = commentEnd + 2;
            continue;
        }

        const start = index;
        const wrapper = WRAPPER_TYPES.find((candidate) => candidate.opener === tagBarText[index]);
        if (wrapper) {
            let depth = 1;
            while (depth < 3 && tagBarText[index + depth] === wrapper.opener) {
                depth += 1;
            }
            const closeToken = wrapper.closer.repeat(depth);
            const closeAt = tagBarText.indexOf(closeToken, index + depth);
            if (closeAt !== -1) {
                index = closeAt + depth;
                tokens.push(tagBarText.slice(start, index));
                continue;
            }
        }

        while (index < tagBarText.length && !/\s/.test(tagBarText[index])) {
            index += 1;
        }
        tokens.push(tagBarText.slice(start, index));
    }
    return tokens;
}

export function chooseStyleScope(contentText, tagBarText) {
    requireText(contentText, 'contentText');
    requireText(tagBarText, 'tagBarText');

    for (let depth = 1; depth <= 3; depth += 1) {
        for (const wrapper of WRAPPER_TYPES) {
            const openToken = wrapper.opener.repeat(depth);
            const closeToken = wrapper.closer.repeat(depth);
            let contentUsesScope = contentText.includes(openToken);
            if (contentText.includes(closeToken)) {
                contentUsesScope = true;
            }
            let tagBarUsesScope = tagBarText.includes(openToken);
            if (tagBarText.includes(closeToken)) {
                tagBarUsesScope = true;
            }
            if (contentUsesScope || tagBarUsesScope) {
                continue;
            }
            return Object.freeze({
                opener: wrapper.opener,
                closer: wrapper.closer,
                depth,
                openToken,
                closeToken,
            });
        }
    }

    throw new Error('No unused style scope delimiter remains for this note');
}

export function buildStyleApplicationPlan(options) {
    if (!options || typeof options !== 'object') {
        throw new Error('buildStyleApplicationPlan requires options');
    }
    const { styleTag, contentText, tagBarText, hasSelection } = options;
    requireKnownStyleTag(styleTag);
    requireText(contentText, 'contentText');
    requireText(tagBarText, 'tagBarText');
    if (typeof hasSelection !== 'boolean') {
        throw new Error('hasSelection must be a boolean');
    }

    if (!hasSelection) {
        return Object.freeze({
            styleTag,
            tagToken: styleTag,
            openToken: '',
            closeToken: '',
        });
    }

    const scope = chooseStyleScope(contentText, tagBarText);
    return Object.freeze({
        styleTag,
        tagToken: `${scope.openToken}${styleTag}${scope.closeToken}`,
        openToken: scope.openToken,
        closeToken: scope.closeToken,
    });
}

export function appendStyleTagToken(tagBarText, tagToken) {
    requireText(tagBarText, 'tagBarText');
    requireText(tagToken, 'tagToken');
    if (tagToken.length === 0) {
        throw new Error('tagToken must not be empty');
    }

    const normalizedTarget = tagToken.toLowerCase();
    const tokens = scanTopLevelTagTokens(tagBarText);
    if (tokens.some((token) => token.toLowerCase() === normalizedTarget)) {
        return tagBarText.trim();
    }
    const existing = tagBarText.trim();
    return existing.length > 0 ? `${existing} ${tagToken}` : tagToken;
}
