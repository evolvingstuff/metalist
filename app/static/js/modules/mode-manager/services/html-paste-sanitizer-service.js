import { CONFIG } from '../../config.js';
import {
    estimateDataUrlPayloadBytes,
    recompressDataImageUrlForEmbedding,
} from './embedded-image-service.js';

const ELEMENT_NODE = 1;
const TEXT_NODE = 3;
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
const AVATAR_HINT_PATTERN = /(avatar|profile|pfp|user.?icon|user.?image|community.?icon|snoo|commenter)/i;
const TIME_HINT_PATTERN = /\b(?:edited\s+)?\d+\s*(?:s|m|min|h|d|w|mo|y)\s*ago\b/i;
const META_HINT_PATTERN = /\b(?:op|edited|top\s+\d+%?\s+commenter)\b/i;
const SCORE_HINT_PATTERN = /^\d+(?:\.\d+)?k?$/i;
const LINE_BREAK_PATTERN = /\r\n|\r|\n/;
const STRUCTURED_LINE_PATTERN = /^\s*(?:[-*+\u2022]\s+|\d+[.)]\s+|\(?\d{1,2}:\d{2}(?::\d{2})?\)?\s*(?:[-\u2013\u2014:]|\s)|[A-Za-z][A-Za-z0-9 /_-]{0,48}:\s*)/;
const AVATAR_CLAMP_PX = 48;
const TREE_WALKER_SHOW_ELEMENT_AND_TEXT = 0x1 | 0x4;
const TREE_WALKER_SHOW_TEXT = 0x4;
const AVATAR_FORWARD_SCAN_NODE_LIMIT = 140;
const AVATAR_BACKWARD_SCAN_NODE_LIMIT = 40;

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

function isSafeDataImageUrl(value) {
    if (typeof value !== 'string') {
        throw new Error('isSafeDataImageUrl expects string input');
    }

    const trimmed = value.trim();
    if (!DATA_IMAGE_URL_PATTERN.test(trimmed)) {
        return false;
    }

    const bytes = estimateDataUrlPayloadBytes(trimmed);
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

function isRecognizedDataImageUrl(value) {
    if (typeof value !== 'string') {
        throw new Error('isRecognizedDataImageUrl expects string input');
    }
    const trimmed = value.trim();
    return DATA_IMAGE_URL_PATTERN.test(trimmed);
}

export function sanitizePastedImageSourceUrl(rawValue) {
    if (typeof rawValue !== 'string') {
        throw new Error('sanitizePastedImageSourceUrl expects rawValue string');
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

    if (scheme === 'data') {
        if (!isRecognizedDataImageUrl(trimmed)) {
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
        if (/^(?:baseline|middle|top|bottom|text-top|text-bottom|sub|super)$/i.test(propertyValue)) {
            return true;
        }
        return isSafeLengthValue(propertyValue);
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

function parseLengthFromInlineStyle(styleValue, propertyName) {
    if (typeof styleValue !== 'string') {
        throw new Error('parseLengthFromInlineStyle expects styleValue string');
    }
    if (typeof propertyName !== 'string') {
        throw new Error('parseLengthFromInlineStyle expects propertyName string');
    }

    const escaped = propertyName.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const pattern = new RegExp(`${escaped}\\s*:\\s*([0-9]+(?:\\.[0-9]+)?)px`, 'i');
    const match = styleValue.match(pattern);
    if (!match || typeof match[1] !== 'string') {
        return null;
    }

    const parsed = Number.parseFloat(match[1]);
    if (!Number.isFinite(parsed) || parsed <= 0) {
        return null;
    }
    return parsed;
}

function parseLengthAttributeValue(attributeValue) {
    if (typeof attributeValue !== 'string') {
        return null;
    }

    const trimmed = attributeValue.trim();
    if (!/^\d+(?:\.\d+)?$/.test(trimmed)) {
        return null;
    }

    const parsed = Number.parseFloat(trimmed);
    if (!Number.isFinite(parsed) || parsed <= 0) {
        return null;
    }
    return parsed;
}

function getImageDeclaredDimensions(sourceImageElement) {
    if (!sourceImageElement) {
        throw new Error('getImageDeclaredDimensions expects sourceImageElement');
    }
    if (!(sourceImageElement instanceof Element)) {
        throw new Error('getImageDeclaredDimensions expects DOM Element');
    }

    const widthAttr = parseLengthAttributeValue(sourceImageElement.getAttribute('width'));
    const heightAttr = parseLengthAttributeValue(sourceImageElement.getAttribute('height'));
    const styleValue = sourceImageElement.getAttribute('style');

    let width = widthAttr;
    if (width === null && typeof styleValue === 'string') {
        width = parseLengthFromInlineStyle(styleValue, 'width');
    }

    let height = heightAttr;
    if (height === null && typeof styleValue === 'string') {
        height = parseLengthFromInlineStyle(styleValue, 'height');
    }

    return { width, height };
}

function normalizeText(value) {
    if (typeof value !== 'string') {
        throw new Error('normalizeText expects string');
    }
    return value.replace(/\s+/g, ' ').trim();
}

function collectAvatarContextSignalsFromText(rawText, signals) {
    if (typeof rawText !== 'string') {
        return;
    }
    const content = normalizeText(rawText);
    if (content.length === 0) {
        return;
    }

    const lowered = content.toLowerCase();
    if (TIME_HINT_PATTERN.test(lowered)) {
        signals.foundTime = true;
    }
    if (META_HINT_PATTERN.test(lowered)) {
        signals.foundOpMeta = true;
    }
}

function getSiblingContextTokens(imageElement) {
    if (!imageElement) {
        throw new Error('getSiblingContextTokens expects imageElement');
    }
    if (!(imageElement instanceof Element)) {
        throw new Error('getSiblingContextTokens expects DOM Element');
    }

    const parent = imageElement.parentNode;
    if (!parent || !('childNodes' in parent)) {
        return [];
    }

    const siblings = Array.from(parent.childNodes);
    let imageIndex = -1;
    let i = 0;
    while (i < siblings.length) {
        if (siblings[i] === imageElement) {
            imageIndex = i;
            break;
        }
        i += 1;
    }
    if (imageIndex < 0) {
        return [];
    }

    let start = imageIndex - 3;
    if (start < 0) {
        start = 0;
    }

    let end = imageIndex + 4;
    if (end > siblings.length) {
        end = siblings.length;
    }

    const tokens = [];
    let cursor = start;
    while (cursor < end) {
        if (cursor !== imageIndex) {
            const node = siblings[cursor];
            if (node.nodeType === 3) {
                const textNode = node;
                const content = textNode.textContent;
                if (typeof content === 'string') {
                    const normalized = normalizeText(content);
                    if (normalized.length > 0) {
                        tokens.push(normalized);
                    }
                }
            } else if (node.nodeType === 1) {
                const element = node;
                if (!(element instanceof Element)) {
                    throw new Error('Expected Element for nodeType 1 in getSiblingContextTokens');
                }
                const content = element.textContent;
                if (typeof content === 'string') {
                    const normalized = normalizeText(content);
                    if (normalized.length > 0) {
                        tokens.push(normalized);
                    }
                }
            }
        }
        cursor += 1;
    }

    return tokens;
}

function hasNearbyAuthorTimeContext(imageElement) {
    if (!imageElement) {
        throw new Error('hasNearbyAuthorTimeContext expects imageElement');
    }
    if (!(imageElement instanceof Element)) {
        throw new Error('hasNearbyAuthorTimeContext expects DOM Element');
    }

    const documentRoot = imageElement.ownerDocument;
    if (!documentRoot || !documentRoot.body) {
        throw new Error('hasNearbyAuthorTimeContext requires ownerDocument.body');
    }
    if (typeof documentRoot.createTreeWalker !== 'function') {
        throw new Error('hasNearbyAuthorTimeContext requires document.createTreeWalker');
    }

    const walker = documentRoot.createTreeWalker(
        documentRoot.body,
        TREE_WALKER_SHOW_ELEMENT_AND_TEXT
    );

    const orderedNodes = [];
    while (walker.nextNode()) {
        orderedNodes.push(walker.currentNode);
    }

    let imageIndex = -1;
    let i = 0;
    while (i < orderedNodes.length) {
        if (orderedNodes[i] === imageElement) {
            imageIndex = i;
            break;
        }
        i += 1;
    }
    if (imageIndex < 0) {
        return false;
    }

    let startIndex = imageIndex - AVATAR_BACKWARD_SCAN_NODE_LIMIT;
    if (startIndex < 0) {
        startIndex = 0;
    }
    let endIndex = imageIndex + AVATAR_FORWARD_SCAN_NODE_LIMIT;
    if (endIndex > orderedNodes.length) {
        endIndex = orderedNodes.length;
    }

    const signals = {
        foundLink: false,
        foundShortHandleLink: false,
        foundTime: false,
        foundOpMeta: false,
    };

    let cursor = startIndex;
    while (cursor < endIndex) {
        const node = orderedNodes[cursor];

        if (node.nodeType === ELEMENT_NODE) {
            const element = node;
            if (!(element instanceof Element)) {
                cursor += 1;
                continue;
            }

            const tagName = element.tagName.toLowerCase();
            if (cursor > imageIndex && tagName === 'img') {
                break;
            }

            if (tagName === 'a') {
                const linkTextContent = element.textContent;
                if (typeof linkTextContent === 'string') {
                    const linkText = normalizeText(linkTextContent);
                    if (linkText.length > 0) {
                        signals.foundLink = true;
                        if (linkText.length <= 48) {
                            signals.foundShortHandleLink = true;
                        }
                    }
                }
            }

            const elementTextContent = element.textContent;
            if (typeof elementTextContent === 'string') {
                collectAvatarContextSignalsFromText(elementTextContent, signals);
            }
        } else if (node.nodeType === 3) {
            const textNodeContent = node.textContent;
            if (typeof textNodeContent === 'string') {
                collectAvatarContextSignalsFromText(textNodeContent, signals);
            }
        }

        if ((signals.foundLink || signals.foundShortHandleLink) && signals.foundTime) {
            return true;
        }
        cursor += 1;
    }

    if (signals.foundShortHandleLink && signals.foundTime) {
        return true;
    }
    if (signals.foundLink && signals.foundOpMeta && signals.foundTime) {
        return true;
    }
    return false;
}

function buildImageSourceFrequencyMap(rootNode) {
    if (!rootNode) {
        throw new Error('buildImageSourceFrequencyMap expects rootNode');
    }
    if (!(rootNode instanceof Element)) {
        throw new Error('buildImageSourceFrequencyMap expects DOM Element rootNode');
    }

    const map = new Map();
    const images = Array.from(rootNode.querySelectorAll('img[src]'));

    let i = 0;
    while (i < images.length) {
        const src = images[i].getAttribute('src');
        if (typeof src === 'string' && src.trim().length > 0) {
            const key = src.trim();
            const existing = map.get(key);
            if (typeof existing === 'number') {
                map.set(key, existing + 1);
            } else {
                map.set(key, 1);
            }
        }
        i += 1;
    }

    return map;
}

function isLikelyAvatarImage(sourceImageElement, imageSourceFrequencyMap) {
    if (!sourceImageElement) {
        throw new Error('isLikelyAvatarImage expects sourceImageElement');
    }
    if (!(sourceImageElement instanceof Element)) {
        throw new Error('isLikelyAvatarImage expects DOM Element');
    }
    if (!(imageSourceFrequencyMap instanceof Map)) {
        throw new Error('isLikelyAvatarImage expects imageSourceFrequencyMap Map');
    }

    let score = 0;

    const classValue = sourceImageElement.getAttribute('class');
    const altValue = sourceImageElement.getAttribute('alt');
    const srcValue = sourceImageElement.getAttribute('src');
    const idValue = sourceImageElement.getAttribute('id');
    const ariaLabel = sourceImageElement.getAttribute('aria-label');

    const hints = [classValue, altValue, srcValue, idValue, ariaLabel];
    let i = 0;
    while (i < hints.length) {
        const hint = hints[i];
        if (typeof hint === 'string' && AVATAR_HINT_PATTERN.test(hint)) {
            score += 3;
            break;
        }
        i += 1;
    }

    if (typeof srcValue === 'string') {
        const key = srcValue.trim();
        const frequency = imageSourceFrequencyMap.get(key);
        if (typeof frequency === 'number' && frequency >= 2) {
            score += 2;
        }
    }

    const dimensions = getImageDeclaredDimensions(sourceImageElement);
    if (dimensions.width !== null && dimensions.height !== null) {
        let ratio = dimensions.width / dimensions.height;
        if (ratio < 1) {
            ratio = dimensions.height / dimensions.width;
        }
        if (ratio <= 1.25 && dimensions.width <= 256 && dimensions.height <= 256) {
            score += 1;
        }
    }

    const tokens = getSiblingContextTokens(sourceImageElement);
    let hasTimeHint = false;
    let hasMetaHint = false;
    let hasScoreHint = false;
    let hasHandleToken = false;

    let j = 0;
    while (j < tokens.length) {
        const token = tokens[j];
        if (TIME_HINT_PATTERN.test(token)) {
            hasTimeHint = true;
        }
        if (META_HINT_PATTERN.test(token)) {
            hasMetaHint = true;
        }
        if (SCORE_HINT_PATTERN.test(token)) {
            hasScoreHint = true;
        }
        if (/^[a-z0-9_-]{3,}$/i.test(token)) {
            hasHandleToken = true;
        }
        j += 1;
    }

    if (hasTimeHint && hasHandleToken) {
        score += 2;
    }
    if (hasMetaHint) {
        score += 1;
    }
    if (hasScoreHint) {
        score += 1;
    }

    if (hasNearbyAuthorTimeContext(sourceImageElement)) {
        score += 4;
    }

    return score >= 4;
}

function clampAvatarImageSize(imageElement) {
    if (!imageElement) {
        throw new Error('clampAvatarImageSize expects imageElement');
    }
    if (!(imageElement instanceof Element)) {
        throw new Error('clampAvatarImageSize expects DOM Element');
    }

    const clampedStyle = `width: ${AVATAR_CLAMP_PX}px; height: ${AVATAR_CLAMP_PX}px; max-width: ${AVATAR_CLAMP_PX}px; max-height: ${AVATAR_CLAMP_PX}px; vertical-align: middle;`;
    imageElement.setAttribute('style', clampedStyle);
}

function clampGeneralImageSize(imageElement) {
    if (!imageElement) {
        throw new Error('clampGeneralImageSize expects imageElement');
    }
    if (!(imageElement instanceof Element)) {
        throw new Error('clampGeneralImageSize expects DOM Element');
    }

    imageElement.removeAttribute('width');
    imageElement.removeAttribute('height');

    const existingStyle = imageElement.getAttribute('style');
    const clampStyle = 'max-width: 100%; width: auto; height: auto;';
    if (typeof existingStyle === 'string' && existingStyle.trim().length > 0) {
        imageElement.setAttribute('style', `${existingStyle} ${clampStyle}`);
    } else {
        imageElement.setAttribute('style', clampStyle);
    }
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

function sanitizeElementAttributes(element, imageSourceFrequencyMap) {
    if (!element) {
        throw new Error('sanitizeElementAttributes expects element');
    }
    if (!(element instanceof Element)) {
        throw new Error('sanitizeElementAttributes expects DOM Element');
    }
    if (!(imageSourceFrequencyMap instanceof Map)) {
        throw new Error('sanitizeElementAttributes expects imageSourceFrequencyMap Map');
    }

    const tagName = element.tagName.toLowerCase();
    const isImageTag = tagName === 'img';
    let shouldClampAvatarImage = false;
    if (isImageTag) {
        shouldClampAvatarImage = isLikelyAvatarImage(element, imageSourceFrequencyMap);
    }
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
            let safeUrl = null;
            if (isImageTag && lowerName === 'src') {
                safeUrl = sanitizePastedImageSourceUrl(rawValue);
            } else {
                safeUrl = sanitizeUrlAttributeValue(rawValue, mode);
            }
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

    if (isImageTag) {
        const src = element.getAttribute('src');
        const hasSrc = typeof src === 'string' && src.trim().length > 0;
        if (!hasSrc) {
            element.remove();
            return;
        }

        if (shouldClampAvatarImage) {
            clampAvatarImageSize(element);
            return;
        }
        clampGeneralImageSize(element);
    }
}

function sanitizeTree(rootNode, imageSourceFrequencyMap) {
    if (!rootNode) {
        throw new Error('sanitizeTree expects rootNode');
    }
    if (!(imageSourceFrequencyMap instanceof Map)) {
        throw new Error('sanitizeTree expects imageSourceFrequencyMap Map');
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

        sanitizeElementAttributes(element, imageSourceFrequencyMap);

        const children = Array.from(element.childNodes);
        let i = 0;
        while (i < children.length) {
            queue.push(children[i]);
            i += 1;
        }
    }
}

export function splitMeaningfulTextLineBreaks(rawText) {
    if (typeof rawText !== 'string') {
        throw new Error('splitMeaningfulTextLineBreaks expects rawText string');
    }
    if (!/[\r\n]/.test(rawText)) {
        return null;
    }
    if (rawText.trim().length === 0) {
        return null;
    }

    return rawText.replace(/\r\n/g, '\n').replace(/\r/g, '\n').split('\n');
}

function hasStructuredLineBreaks(lines) {
    if (!Array.isArray(lines)) {
        throw new Error('hasStructuredLineBreaks expects lines array');
    }

    let nonEmptyLineCount = 0;
    let structuredLineCount = 0;
    let emptyInteriorLineCount = 0;

    let i = 0;
    while (i < lines.length) {
        const line = lines[i];
        if (typeof line !== 'string') {
            throw new Error('hasStructuredLineBreaks expects string lines');
        }

        if (line.trim().length === 0) {
            if (i > 0 && i < lines.length - 1) {
                emptyInteriorLineCount += 1;
            }
            i += 1;
            continue;
        }

        nonEmptyLineCount += 1;
        if (STRUCTURED_LINE_PATTERN.test(line)) {
            structuredLineCount += 1;
        }
        i += 1;
    }

    if (emptyInteriorLineCount > 0) {
        return true;
    }
    if (structuredLineCount >= 2) {
        return true;
    }
    if (structuredLineCount === 1 && nonEmptyLineCount <= 2) {
        return true;
    }
    return false;
}

export function normalizeSoftWrappedTextLineBreaks(rawText) {
    if (typeof rawText !== 'string') {
        throw new Error('normalizeSoftWrappedTextLineBreaks expects rawText string');
    }
    if (!LINE_BREAK_PATTERN.test(rawText)) {
        return rawText;
    }
    if (rawText.trim().length === 0) {
        return rawText;
    }

    const normalizedLines = rawText.replace(/\r\n/g, '\n').replace(/\r/g, '\n').split('\n');
    if (hasStructuredLineBreaks(normalizedLines)) {
        return rawText;
    }

    return rawText
        .replace(/[ \t]*-\s*(?:\r\n|\r|\n)\s*/g, '-')
        .replace(/[ \t]*(?:\r\n|\r|\n)[ \t]*/g, ' ')
        .replace(/ {2,}/g, ' ');
}

function replaceTextNodeWithLineBreaks(documentRoot, textNode, parts) {
    if (!documentRoot) {
        throw new Error('replaceTextNodeWithLineBreaks expects documentRoot');
    }
    if (!textNode || textNode.nodeType !== TEXT_NODE) {
        throw new Error('replaceTextNodeWithLineBreaks expects text node');
    }
    if (!Array.isArray(parts)) {
        throw new Error('replaceTextNodeWithLineBreaks expects parts array');
    }

    const parent = textNode.parentNode;
    if (!parent) {
        throw new Error('Cannot replace detached text node with line breaks');
    }

    const fragment = documentRoot.createDocumentFragment();
    let i = 0;
    while (i < parts.length) {
        if (i > 0) {
            fragment.appendChild(documentRoot.createElement('br'));
        }

        const part = parts[i];
        if (typeof part !== 'string') {
            throw new Error('replaceTextNodeWithLineBreaks expects string parts');
        }
        if (part.length > 0) {
            fragment.appendChild(documentRoot.createTextNode(part));
        }
        i += 1;
    }

    parent.replaceChild(fragment, textNode);
}

function preserveLiteralTextLineBreaks(rootNode) {
    if (!rootNode) {
        throw new Error('preserveLiteralTextLineBreaks expects rootNode');
    }
    if (!(rootNode instanceof Element)) {
        throw new Error('preserveLiteralTextLineBreaks expects DOM Element rootNode');
    }

    const documentRoot = rootNode.ownerDocument;
    if (!documentRoot) {
        throw new Error('preserveLiteralTextLineBreaks requires ownerDocument');
    }
    if (typeof documentRoot.createTreeWalker !== 'function') {
        throw new Error('preserveLiteralTextLineBreaks requires document.createTreeWalker');
    }

    const walker = documentRoot.createTreeWalker(rootNode, TREE_WALKER_SHOW_TEXT);
    const textNodes = [];
    while (walker.nextNode()) {
        const textNode = walker.currentNode;
        if (!textNode || textNode.nodeType !== TEXT_NODE) {
            throw new Error('preserveLiteralTextLineBreaks encountered non-text node');
        }
        textNodes.push(textNode);
    }

    let i = 0;
    while (i < textNodes.length) {
        const textNode = textNodes[i];
        const rawText = textNode.textContent;
        if (typeof rawText !== 'string') {
            throw new Error('preserveLiteralTextLineBreaks expects textContent string');
        }

        const normalizedText = normalizeSoftWrappedTextLineBreaks(rawText);
        if (normalizedText !== rawText) {
            textNode.textContent = normalizedText;
            i += 1;
            continue;
        }

        const parts = splitMeaningfulTextLineBreaks(normalizedText);
        if (parts !== null) {
            replaceTextNodeWithLineBreaks(documentRoot, textNode, parts);
        }
        i += 1;
    }
}

async function recompressEmbeddedDataImageElements(rootNode) {
    if (!rootNode) {
        throw new Error('recompressEmbeddedDataImageElements expects rootNode');
    }

    const images = Array.from(rootNode.querySelectorAll('img[src]'));
    const rewrittenSources = new Map();

    let i = 0;
    while (i < images.length) {
        const image = images[i];
        if (!(image instanceof Element)) {
            throw new Error('recompressEmbeddedDataImageElements encountered non-Element image');
        }
        const rawSource = image.getAttribute('src');
        if (typeof rawSource !== 'string') {
            i += 1;
            continue;
        }
        const source = rawSource.trim();
        if (!isRecognizedDataImageUrl(source)) {
            i += 1;
            continue;
        }

        let rewrittenSource = null;
        if (rewrittenSources.has(source)) {
            rewrittenSource = rewrittenSources.get(source);
        } else {
            rewrittenSource = await recompressDataImageUrlForEmbedding(source);
            rewrittenSources.set(source, rewrittenSource);
        }

        if (typeof rewrittenSource !== 'string' || rewrittenSource.length === 0) {
            image.remove();
            i += 1;
            continue;
        }

        image.setAttribute('src', rewrittenSource);
        i += 1;
    }
}

export async function sanitizeExternalClipboardHtml(rawHtml) {
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

    const imageSourceFrequencyMap = buildImageSourceFrequencyMap(parsed.body);
    sanitizeTree(parsed.body, imageSourceFrequencyMap);
    preserveLiteralTextLineBreaks(parsed.body);
    await recompressEmbeddedDataImageElements(parsed.body);
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

function restoreSelectionRange(selectionRange) {
    if (selectionRange === null) {
        return;
    }
    if (!(selectionRange instanceof Range)) {
        throw new Error('restoreSelectionRange expects Range or null');
    }

    const selection = window.getSelection();
    if (!selection) {
        throw new Error('Selection missing while restoring paste range');
    }

    selection.removeAllRanges();
    selection.addRange(selectionRange.cloneRange());
}

export async function sanitizeAndInsertExternalPaste(event, selectionRange) {
    if (!event) {
        throw new Error('sanitizeAndInsertExternalPaste expects paste event');
    }
    if (!event.clipboardData) {
        return false;
    }
    if (selectionRange !== null && !(selectionRange instanceof Range)) {
        throw new Error('sanitizeAndInsertExternalPaste expects Range or null selectionRange');
    }

    const rawHtml = event.clipboardData.getData('text/html');
    if (typeof rawHtml === 'string' && rawHtml.length > 0) {
        const sanitizedHtml = await sanitizeExternalClipboardHtml(rawHtml);
        if (sanitizedHtml.length > 0) {
            restoreSelectionRange(selectionRange);
            return insertHtmlAtSelection(sanitizedHtml);
        }
    }

    const plainText = event.clipboardData.getData('text/plain');
    if (typeof plainText === 'string' && plainText.length > 0) {
        restoreSelectionRange(selectionRange);
        return insertPlainTextAtSelection(plainText);
    }
    return false;
}
