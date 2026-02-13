const META_LATEX_SELECTOR = '.meta-latex';
const LATEX_RENDERED_ATTR = 'latex-rendered';
const LATEX_PLACEHOLDER_RE = /@@MLLATEX\[([A-Za-z0-9+/=]+)\]@@/g;
let warnedMissingKatex = false;

function escapeHtml(value) {
    if (typeof value !== 'string') {
        throw new Error('escapeHtml requires a string');
    }
    return value
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

function getKatexRenderer() {
    const katex = window.katex;
    if (!katex || typeof katex.renderToString !== 'function') {
        return null;
    }
    return katex;
}

function isEscaped(text, index) {
    let count = 0;
    let cursor = index - 1;
    while (cursor >= 0 && text[cursor] === '\\') {
        count += 1;
        cursor -= 1;
    }
    return count % 2 === 1;
}

function decodeLatexPlaceholderPayload(encoded) {
    if (typeof encoded !== 'string') {
        throw new Error('decodeLatexPlaceholderPayload requires encoded string');
    }
    let decodedText = '';
    try {
        decodedText = window.atob(encoded);
    } catch (error) {
        return null;
    }
    let payload = null;
    try {
        payload = JSON.parse(decodedText);
    } catch (error) {
        return null;
    }
    if (!payload || typeof payload !== 'object') {
        return null;
    }
    if (typeof payload.text !== 'string') {
        return null;
    }
    let classes = '';
    if (typeof payload.classes === 'string') {
        classes = payload.classes;
    }
    return { text: payload.text, classes };
}

export function replaceLatexPlaceholders(rootElement) {
    if (!rootElement) {
        throw new Error('replaceLatexPlaceholders requires a root element');
    }
    const walker = document.createTreeWalker(rootElement, NodeFilter.SHOW_TEXT);
    const textNodes = [];
    while (walker.nextNode()) {
        textNodes.push(walker.currentNode);
    }
    textNodes.forEach((textNode) => {
        const text = textNode.nodeValue;
        if (typeof text !== 'string') {
            return;
        }
        if (text.indexOf('@@MLLATEX[') === -1) {
            return;
        }
        LATEX_PLACEHOLDER_RE.lastIndex = 0;
        if (!LATEX_PLACEHOLDER_RE.exec(text)) {
            return;
        }
        LATEX_PLACEHOLDER_RE.lastIndex = 0;
        const fragment = document.createDocumentFragment();
        let cursor = 0;
        let match = LATEX_PLACEHOLDER_RE.exec(text);
        while (match) {
            const start = match.index;
            if (start > cursor) {
                fragment.appendChild(document.createTextNode(text.slice(cursor, start)));
            }
            const payload = decodeLatexPlaceholderPayload(match[1]);
            if (!payload) {
                fragment.appendChild(document.createTextNode(match[0]));
            } else {
                const span = document.createElement('span');
                let className = 'meta-latex';
                if (payload.classes !== '') {
                    className = `${className} ${payload.classes}`;
                }
                span.className = className;
                span.textContent = payload.text;
                fragment.appendChild(span);
            }
            cursor = start + match[0].length;
            match = LATEX_PLACEHOLDER_RE.exec(text);
        }
        if (cursor < text.length) {
            fragment.appendChild(document.createTextNode(text.slice(cursor)));
        }
        const parent = textNode.parentNode;
        if (!parent) {
            return;
        }
        parent.replaceChild(fragment, textNode);
    });
}

function findClosingDelimiter(text, startIndex, delimiter) {
    let cursor = startIndex;
    while (cursor < text.length) {
        if (text.startsWith(delimiter, cursor) && !isEscaped(text, cursor)) {
            return cursor;
        }
        cursor += 1;
    }
    return -1;
}

function findInlineClosing(text, startIndex) {
    let cursor = startIndex;
    while (cursor < text.length) {
        if (text[cursor] === '$' && !isEscaped(text, cursor) && text[cursor + 1] !== '$') {
            return cursor;
        }
        cursor += 1;
    }
    return -1;
}

function parseLatexSegments(text) {
    const segments = [];
    let cursor = 0;
    let lastTextStart = 0;

    const flushText = (endIndex) => {
        if (endIndex > lastTextStart) {
            segments.push({ type: 'text', value: text.slice(lastTextStart, endIndex) });
        }
    };

    while (cursor < text.length) {
        if (text.startsWith('$$', cursor) && !isEscaped(text, cursor)) {
            const closeIndex = findClosingDelimiter(text, cursor + 2, '$$');
            if (closeIndex !== -1) {
                flushText(cursor);
                segments.push({ type: 'display', value: text.slice(cursor + 2, closeIndex) });
                cursor = closeIndex + 2;
                lastTextStart = cursor;
                continue;
            }
        }

        if (text[cursor] === '$' && !isEscaped(text, cursor) && text[cursor + 1] !== '$') {
            const closeIndex = findInlineClosing(text, cursor + 1);
            if (closeIndex !== -1) {
                flushText(cursor);
                segments.push({ type: 'inline', value: text.slice(cursor + 1, closeIndex) });
                cursor = closeIndex + 1;
                lastTextStart = cursor;
                continue;
            }
        }

        cursor += 1;
    }

    flushText(text.length);
    return segments;
}

function hasMathDelimiters(text) {
    let cursor = 0;
    while (cursor < text.length) {
        if (text.startsWith('$$', cursor) && !isEscaped(text, cursor)) {
            return true;
        }
        if (text[cursor] === '$' && !isEscaped(text, cursor) && text[cursor + 1] !== '$') {
            return true;
        }
        cursor += 1;
    }
    return false;
}

function renderTextSegment(text) {
    if (text === '') {
        return '';
    }
    const escaped = escapeHtml(text);
    return escaped.replace(/\n/g, '<br>');
}

function renderLatexError(block, source, error) {
    block.innerHTML = '';
    block.classList.add('meta-latex-error');

    const badge = document.createElement('span');
    badge.className = 'meta-latex-badge';
    badge.textContent = 'Invalid LaTeX';
    if (error && typeof error.message === 'string') {
        badge.title = error.message;
    }

    const pre = document.createElement('pre');
    pre.className = 'meta-latex-pre';

    const code = document.createElement('code');
    code.className = 'meta-latex-code';
    code.textContent = source;

    pre.appendChild(code);
    block.appendChild(badge);
    block.appendChild(pre);
}

export function renderLatexBlocks(rootElement) {
    if (!rootElement) {
        throw new Error('renderLatexBlocks requires a root element');
    }
    replaceLatexPlaceholders(rootElement);

    const blocks = rootElement.querySelectorAll(
        `${META_LATEX_SELECTOR}:not([data-${LATEX_RENDERED_ATTR}="true"])`
    );
    if (blocks.length === 0) {
        return;
    }

    const katex = getKatexRenderer();
    if (!katex) {
        if (!warnedMissingKatex) {
            warnedMissingKatex = true;
            console.warn('KaTeX is not available; ensure katex is loaded');
        }
        return;
    }
    blocks.forEach((block) => {
        const rawText = block.textContent;
        const source = rawText === null ? '' : rawText;
        let renderedHtml = '';
        if (!hasMathDelimiters(source)) {
            renderedHtml = katex.renderToString(source, {
                displayMode: true,
                throwOnError: false,
            });
        } else {
            const segments = parseLatexSegments(source);
            const renderedParts = segments.map((segment) => {
                if (segment.type === 'text') {
                    return renderTextSegment(segment.value);
                }
                const displayMode = segment.type === 'display';
                return katex.renderToString(segment.value, {
                    displayMode,
                    throwOnError: false,
                });
            });
            renderedHtml = renderedParts.join('');
        }
        block.innerHTML = renderedHtml;
        block.setAttribute(`data-${LATEX_RENDERED_ATTR}`, 'true');
    });
}

export function renderLatexHtml(htmlText) {
    if (typeof htmlText !== 'string') {
        throw new Error('renderLatexHtml requires htmlText string');
    }
    const katex = getKatexRenderer();
    if (!katex) {
        if (!warnedMissingKatex) {
            warnedMissingKatex = true;
            console.warn('KaTeX is not available; ensure katex is loaded');
        }
        return htmlText;
    }
    const container = document.createElement('div');
    container.innerHTML = htmlText;
    renderLatexBlocks(container);
    return container.innerHTML;
}
