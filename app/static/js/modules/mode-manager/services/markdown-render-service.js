const META_MARKDOWN_SELECTOR = '.meta-markdown';
const MARKDOWN_RENDERED_ATTR = 'markdown-rendered';

let cachedRenderer = null;

function getMarkdownRenderer() {
    if (cachedRenderer) {
        return cachedRenderer;
    }
    const factory = window.markdownit;
    if (typeof factory !== 'function') {
        throw new Error('markdown-it is not available; ensure markdown-it is loaded');
    }
    cachedRenderer = factory({
        html: false,
        linkify: true,
        breaks: true,
    });
    return cachedRenderer;
}

export function renderMarkdownBlocks(rootElement) {
    if (!rootElement) {
        throw new Error('renderMarkdownBlocks requires a root element');
    }
    const blocks = rootElement.querySelectorAll(
        `${META_MARKDOWN_SELECTOR}:not([data-${MARKDOWN_RENDERED_ATTR}="true"])`
    );
    if (blocks.length === 0) {
        return;
    }
    const renderer = getMarkdownRenderer();
    blocks.forEach((block) => {
        const rawText = block.textContent;
        const source = rawText === null ? '' : rawText;
        const rendered = renderer.render(source);
        block.innerHTML = rendered;
        block.setAttribute(`data-${MARKDOWN_RENDERED_ATTR}`, 'true');
    });
}

export function renderMarkdownHtml(htmlText) {
    if (typeof htmlText !== 'string') {
        throw new Error('renderMarkdownHtml requires htmlText string');
    }
    const container = document.createElement('div');
    container.innerHTML = htmlText;
    renderMarkdownBlocks(container);
    return container.innerHTML;
}
