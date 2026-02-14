import { CONFIG } from '../../config.js';

const ELEMENT_NODE = 1;
const COMMENT_NODE = 8;

const BLOCKED_TAGS = new Set([
    'script',
    'style',
    'iframe',
    'object',
    'embed',
    'applet',
    'meta',
    'base',
    'link',
    'svg',
    'math',
    'form',
    'input',
    'button',
    'textarea',
    'select',
    'option',
    'template',
    'noscript',
]);

const URL_ATTRIBUTES = new Set([
    'href',
    'src',
    'xlink:href',
    'action',
    'formaction',
    'poster',
    'background',
    'cite',
    'longdesc',
]);

const SAFE_HREF_SCHEMES = new Set([
    'http',
    'https',
    'mailto',
    'tel',
]);

const SAFE_SRC_SCHEMES = new Set([
    'http',
    'https',
    'blob',
]);

const DANGEROUS_SCHEME_PREFIXES = [
    'javascript:',
    'vbscript:',
    'file:',
    'filesystem:',
    'data:text/html',
    'data:application/',
];

const DATA_IMAGE_URL_PATTERN = /^data:image\/(?:png|jpe?g|gif|webp|bmp|avif);base64,[a-z0-9+/=\s]+$/i;
const DANGEROUS_STYLE_PATTERN = /(?:url\s*\(|expression\s*\(|@import|-moz-binding|behavior\s*:|javascript:|vbscript:|data:text\/html|data:application\/)/i;
const ENCODED_ENTITY_PATTERN = /(?:&#|\\[0-9a-fA-F])/;
const DISALLOWED_STYLE_CHARS_PATTERN = /[<>`]/;
const HIDDEN_STYLE_PATTERN = /(?:^|;)\s*(display\s*:\s*none|visibility\s*:\s*hidden)\s*(?:;|$)/i;

const TEXT_STYLE_PROPERTIES = new Set([
    'white-space',
    'font-weight',
    'font-style',
    'text-decoration',
    'text-decoration-line',
    'vertical-align',
]);

const BLOCK_STYLE_PROPERTIES = new Set([
    'margin-left',
    'padding-left',
    'text-indent',
]);

const IMAGE_STYLE_PROPERTIES = new Set([
    'width',
    'height',
    'max-width',
    'max-height',
]);

const BLOCK_TAGS = new Set([
    'p',
    'div',
    'li',
    'blockquote',
    'pre',
    'code',
    'ul',
    'ol',
    'h1',
    'h2',
    'h3',
    'h4',
    'h5',
    'h6',
    'table',
    'tbody',
    'thead',
    'tfoot',
    'tr',
    'td',
    'th',
]);

function getMaxDataImageBytes() {
    if (!CONFIG || !CONFIG.PASTE) {
        throw new Error('CONFIG.PASTE is required for paste sanitizer');
    }

    const maxBytes = CONFIG.PASTE.MAX_DATA_IMAGE_BYTES;
    if (typeof maxBytes !== 'number') {
        throw new Error('CONFIG.PASTE.MAX_DATA_IMAGE_BYTES must be a number');
    }
    if (!Number.isInteger(maxBytes)) {
        throw new Error('CONFIG.PASTE.MAX_DATA_IMAGE_BYTES must be an integer');
    }
    if (maxBytes <= 0) {
        throw new Error('CONFIG.PASTE.MAX_DATA_IMAGE_BYTES must be > 0');
    }
    return maxBytes;
}

function decodePercentEscapes(input) {
    if (typeof input !== 'string') {
        throw new Error('decodePercentEscapes expects string input');
    }

    return input.replace(/%([0-9a-fA-F]{2})/g, (_, hex) => String.fromCharCode(parseInt(hex, 16)));
}

function normalizeForSchemeCheck(input) {
    if (typeof input !== 'string') {
        throw new Error('normalizeForSchemeCheck expects string input');
    }

    const withoutControls = input.replace(/[\u0000-\u0020\u007f]+/g, '');
    const decoded = decodePercentEscapes(withoutControls);
    return decoded.toLowerCase();
}

function estimateBase64PayloadBytes(dataImageUrl) {
    if (typeof dataImageUrl !== 'string') {
        throw new Error('estimateBase64PayloadBytes expects string input');
    }

    const commaIndex = dataImageUrl.indexOf(',');
    if (commaIndex < 0) {
        return null;
    }

    const payload = dataImageUrl.slice(commaIndex + 1).replace(/\s+/g, '');
    if (payload.length === 0) {
        return 0;
    }

    let paddingBytes = 0;
    if (payload.endsWith('==')) {
        paddingBytes = 2;
    } else if (payload.endsWith('=')) {
        paddingBytes = 1;
    }

    const estimated = Math.floor((payload.length * 3) / 4) - paddingBytes;
    if (estimated < 0) {
        return null;
    }
    return estimated;
}

function isSafeDataImageUrl(value) {
    if (typeof value !== 'string') {
        throw new Error('isSafeDataImageUrl expects string input');
    }

    const trimmed = value.trim();
    if (!DATA_IMAGE_URL_PATTERN.test(trimmed)) {
        return false;
    }

    const bytes = estimateBase64PayloadBytes(trimmed);
    if (bytes === null) {
        return false;
    }

    return bytes <= getMaxDataImageBytes();
}

function startsWithDangerousScheme(normalizedValue) {
    if (typeof normalizedValue !== 'string') {
        throw new Error('startsWithDangerousScheme expects string input');
    }

    let i = 0;
    while (i < DANGEROUS_SCHEME_PREFIXES.length) {
        if (normalizedValue.startsWith(DANGEROUS_SCHEME_PREFIXES[i])) {
            return true;
        }
        i += 1;
    }
    return false;
}

function isRelativeOrAnchorUrl(value) {
    if (typeof value !== 'string') {
        throw new Error('isRelativeOrAnchorUrl expects string input');
    }

    if (value.startsWith('#')) {
        return true;
    }
    if (value.startsWith('/')) {
        return true;
    }
    if (value.startsWith('./')) {
        return true;
    }
    if (value.startsWith('../')) {
        return true;
    }
    if (value.startsWith('//')) {
        return true;
    }
    return false;
}

function extractScheme(value) {
    if (typeof value !== 'string') {
        throw new Error('extractScheme expects string input');
    }

    const match = /^\s*([a-zA-Z][a-zA-Z0-9+.-]*):/.exec(value);
    if (!match) {
        return null;
    }
    return match[1].toLowerCase();
}

export function sanitizeUrlAttributeValue(rawValue, mode) {
    if (typeof rawValue !== 'string') {
        throw new Error('sanitizeUrlAttributeValue expects rawValue string');
    }
    if (typeof mode !== 'string') {
        throw new Error('sanitizeUrlAttributeValue expects mode string');
    }
    if (mode !== 'href' && mode !== 'src') {
        throw new Error(`sanitizeUrlAttributeValue mode must be href or src, received: ${mode}`);
    }

    const trimmed = rawValue.trim();
    if (trimmed.length === 0) {
        return null;
    }

    const normalized = normalizeForSchemeCheck(trimmed);
    if (startsWithDangerousScheme(normalized)) {
        return null;
    }

    if (isRelativeOrAnchorUrl(trimmed)) {
        return trimmed;
    }

    const scheme = extractScheme(trimmed);
    if (scheme === null) {
        return trimmed;
    }

    if (mode === 'href') {
        if (!SAFE_HREF_SCHEMES.has(scheme)) {
            return null;
        }
        return trimmed;
    }

    if (scheme === 'data') {
        if (!isSafeDataImageUrl(trimmed)) {
            return null;
        }
        return trimmed;
    }

    if (!SAFE_SRC_SCHEMES.has(scheme)) {
        return null;
    }
    return trimmed;
}

function isSafeLengthValue(value) {
    if (typeof value !== 'string') {
        throw new Error('isSafeLengthValue expects string input');
    }
    return /^-?\d+(?:\.\d+)?(?:px|em|rem|%)$/.test(value);
}

function isSafeStyleValue(propertyName, propertyValue) {
    if (typeof propertyName !== 'string') {
        throw new Error('isSafeStyleValue expects propertyName string');
    }
    if (typeof propertyValue !== 'string') {
        throw new Error('isSafeStyleValue expects propertyValue string');
    }

    if (propertyName === 'font-weight') {
        return /^(?:normal|bold|bolder|lighter|[1-9]00)$/i.test(propertyValue);
    }
    if (propertyName === 'font-style') {
        return /^(?:normal|italic|oblique)$/i.test(propertyValue);
    }
    if (propertyName === 'white-space') {
        return /^(?:normal|pre|pre-wrap|pre-line|nowrap|break-spaces)$/i.test(propertyValue);
    }
    if (propertyName === 'text-decoration' || propertyName === 'text-decoration-line') {
        return /^(?:none|underline|line-through|overline)(?:\s+(?:underline|line-through|overline))*$/i.test(propertyValue);
    }
    if (propertyName === 'vertical-align') {
        return /^(?:baseline|middle|top|bottom|text-top|text-bottom|sub|super)$/i.test(propertyValue);
    }
    if (propertyName === 'width' || propertyName === 'height' || propertyName === 'max-width' || propertyName === 'max-height') {
        if (propertyValue === 'auto') {
            return true;
        }
        return isSafeLengthValue(propertyValue);
    }
    if (propertyName === 'margin-left' || propertyName === 'padding-left' || propertyName === 'text-indent') {
        return isSafeLengthValue(propertyValue);
    }

    return false;
}

function shouldKeepStyleProperty(propertyName, tagName) {
    if (typeof propertyName !== 'string') {
        throw new Error('shouldKeepStyleProperty expects propertyName string');
    }
    if (typeof tagName !== 'string') {
        throw new Error('shouldKeepStyleProperty expects tagName string');
    }

    if (TEXT_STYLE_PROPERTIES.has(propertyName)) {
        return true;
    }
    if (tagName === 'img' && IMAGE_STYLE_PROPERTIES.has(propertyName)) {
        return true;
    }
    if (BLOCK_TAGS.has(tagName) && BLOCK_STYLE_PROPERTIES.has(propertyName)) {
        return true;
    }
    return false;
}

export function sanitizeStyleAttributeValue(rawStyle, tagName) {
    if (typeof rawStyle !== 'string') {
        throw new Error('sanitizeStyleAttributeValue expects rawStyle string');
    }
    if (typeof tagName !== 'string') {
        throw new Error('sanitizeStyleAttributeValue expects tagName string');
    }

    const declarations = rawStyle.split(';');
    const safeDeclarations = [];

    let i = 0;
    while (i < declarations.length) {
        const declaration = declarations[i].trim();
        if (declaration.length > 0) {
            const colonIndex = declaration.indexOf(':');
            if (colonIndex > 0) {
                const propertyName = declaration.slice(0, colonIndex).trim().toLowerCase();
                const propertyValue = declaration.slice(colonIndex + 1).trim();

                const keepProperty = shouldKeepStyleProperty(propertyName, tagName);
                const safeValue = propertyValue.length > 0
                    && !DANGEROUS_STYLE_PATTERN.test(propertyValue)
                    && !ENCODED_ENTITY_PATTERN.test(propertyValue)
                    && !DISALLOWED_STYLE_CHARS_PATTERN.test(propertyValue)
                    && isSafeStyleValue(propertyName, propertyValue);

                if (keepProperty && safeValue) {
                    safeDeclarations.push(`${propertyName}: ${propertyValue}`);
                }
            }
        }
        i += 1;
    }

    if (safeDeclarations.length === 0) {
        return null;
    }
    return `${safeDeclarations.join('; ')};`;
}

function removeElementPreserveChildren(element) {
    if (!element) {
        throw new Error('removeElementPreserveChildren expects element');
    }
    if (!(element instanceof Element)) {
        throw new Error('removeElementPreserveChildren expects DOM Element');
    }
    const parent = element.parentNode;
    if (!parent) {
        element.remove();
        return;
    }

    while (element.firstChild) {
        parent.insertBefore(element.firstChild, element);
    }
    element.remove();
}

function sanitizeElementAttributes(element) {
    if (!element) {
        throw new Error('sanitizeElementAttributes expects element');
    }
    if (!(element instanceof Element)) {
        throw new Error('sanitizeElementAttributes expects DOM Element');
    }

    const tagName = element.tagName.toLowerCase();
    const attributes = Array.from(element.attributes);

    let i = 0;
    while (i < attributes.length) {
        const attributeName = attributes[i].name;
        const lowerName = attributeName.toLowerCase();
        const rawValue = attributes[i].value;

        if (lowerName.startsWith('on')) {
            element.removeAttribute(attributeName);
            i += 1;
            continue;
        }

        if (lowerName === 'id' || lowerName === 'class' || lowerName.startsWith('data-')) {
            element.removeAttribute(attributeName);
            i += 1;
            continue;
        }

        if (lowerName === 'srcset') {
            element.removeAttribute(attributeName);
            i += 1;
            continue;
        }

        if (lowerName === 'style') {
            if (HIDDEN_STYLE_PATTERN.test(rawValue)) {
                removeElementPreserveChildren(element);
                return;
            }

            const sanitizedStyle = sanitizeStyleAttributeValue(rawValue, tagName);
            if (sanitizedStyle === null) {
                element.removeAttribute(attributeName);
            } else {
                element.setAttribute('style', sanitizedStyle);
            }
            i += 1;
            continue;
        }

        if (URL_ATTRIBUTES.has(lowerName)) {
            let mode = 'src';
            if (lowerName === 'href') {
                mode = 'href';
            }
            const safeUrl = sanitizeUrlAttributeValue(rawValue, mode);
            if (safeUrl === null) {
                element.removeAttribute(attributeName);
            } else {
                element.setAttribute(attributeName, safeUrl);
            }
            i += 1;
            continue;
        }

        i += 1;
    }

    if (tagName === 'a') {
        const href = element.getAttribute('href');
        if (typeof href !== 'string' || href.trim().length === 0) {
            removeElementPreserveChildren(element);
            return;
        }

        const target = element.getAttribute('target');
        if (typeof target === 'string' && target.trim().toLowerCase() === '_blank') {
            element.setAttribute('rel', 'noopener noreferrer');
        }
    }

    if (tagName === 'img') {
        const src = element.getAttribute('src');
        const hasSrc = typeof src === 'string' && src.trim().length > 0;
        if (!hasSrc) {
            element.remove();
        }
    }
}

function sanitizeTree(rootNode) {
    if (!rootNode) {
        throw new Error('sanitizeTree expects rootNode');
    }

    const queue = Array.from(rootNode.childNodes);
    while (queue.length > 0) {
        const node = queue.shift();
        if (!node) {
            continue;
        }

        if (node.nodeType === COMMENT_NODE) {
            node.remove();
            continue;
        }

        if (node.nodeType !== ELEMENT_NODE) {
            continue;
        }

        const element = node;
        if (!(element instanceof Element)) {
            throw new Error('sanitizeTree encountered non-Element node with ELEMENT_NODE type');
        }

        const tagName = element.tagName.toLowerCase();
        if (BLOCKED_TAGS.has(tagName)) {
            element.remove();
            continue;
        }

        const hasHiddenAttribute = element.hasAttribute('hidden');
        const ariaHidden = element.getAttribute('aria-hidden');
        const ariaHiddenIsTrue = typeof ariaHidden === 'string' && ariaHidden.trim().toLowerCase() === 'true';
        if (hasHiddenAttribute || ariaHiddenIsTrue) {
            removeElementPreserveChildren(element);
            continue;
        }

        sanitizeElementAttributes(element);

        const children = Array.from(element.childNodes);
        let i = 0;
        while (i < children.length) {
            queue.push(children[i]);
            i += 1;
        }
    }
}

export function sanitizeExternalClipboardHtml(rawHtml) {
    if (typeof rawHtml !== 'string') {
        throw new Error('sanitizeExternalClipboardHtml expects rawHtml string');
    }
    if (rawHtml.length === 0) {
        return '';
    }
    if (typeof DOMParser !== 'function') {
        throw new Error('DOMParser is required for sanitizeExternalClipboardHtml');
    }

    const parser = new DOMParser();
    const parsed = parser.parseFromString(rawHtml, 'text/html');
    if (!parsed || !parsed.body) {
        throw new Error('Failed to parse clipboard HTML');
    }

    sanitizeTree(parsed.body);
    return parsed.body.innerHTML;
}

function insertHtmlAtSelection(html) {
    if (typeof html !== 'string') {
        throw new Error('insertHtmlAtSelection expects html string');
    }

    const inserted = document.execCommand('insertHTML', false, html);
    if (inserted) {
        return true;
    }

    const selection = window.getSelection();
    if (!selection) {
        throw new Error('Selection missing while inserting HTML');
    }
    if (selection.rangeCount === 0) {
        throw new Error('Selection range missing while inserting HTML');
    }

    const range = selection.getRangeAt(0);
    const fragment = range.createContextualFragment(html);
    const lastNode = fragment.lastChild;
    range.deleteContents();
    range.insertNode(fragment);

    if (lastNode) {
        range.setStartAfter(lastNode);
        range.collapse(true);
        selection.removeAllRanges();
        selection.addRange(range);
    }
    return true;
}

function insertPlainTextAtSelection(text) {
    if (typeof text !== 'string') {
        throw new Error('insertPlainTextAtSelection expects text string');
    }

    const inserted = document.execCommand('insertText', false, text);
    if (inserted) {
        return true;
    }

    const selection = window.getSelection();
    if (!selection) {
        throw new Error('Selection missing while inserting plain text');
    }
    if (selection.rangeCount === 0) {
        throw new Error('Selection range missing while inserting plain text');
    }

    const range = selection.getRangeAt(0);
    range.deleteContents();
    const textNode = document.createTextNode(text);
    range.insertNode(textNode);
    range.setStartAfter(textNode);
    range.collapse(true);
    selection.removeAllRanges();
    selection.addRange(range);
    return true;
}

export function sanitizeAndInsertExternalPaste(event) {
    if (!event) {
        throw new Error('sanitizeAndInsertExternalPaste expects paste event');
    }
    if (!event.clipboardData) {
        return false;
    }

    const rawHtml = event.clipboardData.getData('text/html');
    if (typeof rawHtml === 'string' && rawHtml.length > 0) {
        const sanitizedHtml = sanitizeExternalClipboardHtml(rawHtml);
        if (sanitizedHtml.length > 0) {
            return insertHtmlAtSelection(sanitizedHtml);
        }
    }

    const plainText = event.clipboardData.getData('text/plain');
    if (typeof plainText === 'string' && plainText.length > 0) {
        return insertPlainTextAtSelection(plainText);
    }
    return false;
}
