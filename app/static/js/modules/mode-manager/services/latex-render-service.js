const META_LATEX_SELECTOR = '.meta-latex';
const LATEX_RENDERED_ATTR = 'latex-rendered';
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
        try {
            let renderedHtml = '';
            if (!hasMathDelimiters(source)) {
                renderedHtml = katex.renderToString(source, {
                    displayMode: true,
                    throwOnError: true,
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
                        throwOnError: true,
                    });
                });
                renderedHtml = renderedParts.join('');
            }
            block.innerHTML = renderedHtml;
            block.setAttribute(`data-${LATEX_RENDERED_ATTR}`, 'true');
        } catch (error) {
            renderLatexError(block, source, error);
            block.setAttribute(`data-${LATEX_RENDERED_ATTR}`, 'true');
        }
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
