const STATUS_CONTENT_SELECTOR = '.meta-status-text';
const FIRST_LINE_BOUNDARY_RE = /<br\s*\/?>|<\/?(?:div|p|li|h[1-6]|pre|blockquote|ul|ol|table|tr|td|th|section|article|header|footer|main)\b[^>]*>\s*|\n/gi;
const HTML_TAG_RE = /<[^>]+>/g;
const WHITESPACE_RE = /\s+/g;
const STATUS_PREVIEW_SOURCE_HTML = new WeakMap();

function decodeBasicHtmlEntities(text) {
    if (typeof text !== 'string') {
        throw new Error('decodeBasicHtmlEntities requires a string');
    }

    return text
        .replace(/&nbsp;/gi, ' ')
        .replace(/&amp;/gi, '&')
        .replace(/&lt;/gi, '<')
        .replace(/&gt;/gi, '>')
        .replace(/&quot;/gi, '"')
        .replace(/&#39;/gi, "'");
}

function normalizePreviewLine(line) {
    if (typeof line !== 'string') {
        throw new Error('normalizePreviewLine requires a string');
    }

    const withoutTags = line.replace(HTML_TAG_RE, ' ');
    const decoded = decodeBasicHtmlEntities(withoutTags);
    return decoded.replace(WHITESPACE_RE, ' ').trim();
}

export function extractCollapsedStatusPreviewFromHtml(sourceHtml) {
    if (typeof sourceHtml !== 'string') {
        throw new Error('extractCollapsedStatusPreviewFromHtml requires a string');
    }

    const normalizedLines = sourceHtml
        .replace(FIRST_LINE_BOUNDARY_RE, '\n')
        .split('\n')
        .map(normalizePreviewLine)
        .filter((line) => line.length > 0);

    return {
        previewText: normalizedLines[0] || '',
        hasAdditionalLines: normalizedLines.length > 1,
    };
}

function getStatusTextElement(contentElement) {
    if (!contentElement || typeof contentElement.querySelector !== 'function') {
        throw new Error('getStatusTextElement requires a content element');
    }

    return contentElement.querySelector(STATUS_CONTENT_SELECTOR);
}

export function getCollapsedStatusPreviewState(contentElement) {
    const statusTextElement = getStatusTextElement(contentElement);
    if (!statusTextElement) {
        return null;
    }

    let sourceHtml = STATUS_PREVIEW_SOURCE_HTML.get(statusTextElement);
    if (typeof sourceHtml !== 'string') {
        sourceHtml = statusTextElement.innerHTML;
        STATUS_PREVIEW_SOURCE_HTML.set(statusTextElement, sourceHtml);
    }

    const preview = extractCollapsedStatusPreviewFromHtml(sourceHtml);
    return {
        statusTextElement,
        sourceHtml,
        previewText: preview.previewText,
        hasAdditionalLines: preview.hasAdditionalLines,
    };
}

export function syncCollapsedStatusPreview(contentElement, isCollapsed) {
    if (typeof isCollapsed !== 'boolean') {
        throw new Error('syncCollapsedStatusPreview requires boolean collapsed state');
    }

    const previewState = getCollapsedStatusPreviewState(contentElement);
    if (!previewState) {
        return null;
    }

    const { statusTextElement, sourceHtml, previewText, hasAdditionalLines } = previewState;
    if (!isCollapsed || !hasAdditionalLines || previewText.length === 0) {
        if (statusTextElement.innerHTML !== sourceHtml) {
            statusTextElement.innerHTML = sourceHtml;
        }
        return previewState;
    }

    const collapsedPreviewText = `${previewText}...`;
    if (statusTextElement.textContent !== collapsedPreviewText || statusTextElement.children.length > 0) {
        statusTextElement.textContent = collapsedPreviewText;
    }
    return previewState;
}
