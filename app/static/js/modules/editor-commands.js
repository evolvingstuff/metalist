import { ModeContextInstance as ModeContext } from './mode-manager/mode-context.js';
import { DOMUtils } from './dom-utils.js';
import {
    getActiveEditable,
    getActiveNoteId,
    restoreSelection,
    captureSelectionSnapshot,
} from './editor-selection.js';

function ensureActiveEditable() {
    const editable = getActiveEditable();
    if (!editable) {
        throw new Error('No active editable region for formatting command');
    }
    return editable;
}

function syncModeContextContent() {
    const noteId = getActiveNoteId();
    if (!noteId) {
        return;
    }
    const noteElement = DOMUtils.getNoteById(noteId);
    const html = DOMUtils.getNoteContentHTML(noteElement);
    if (ModeContext.currentContent !== html) {
        ModeContext.setCurrentContent(html);
    }
    if (!ModeContext.isDirty) {
        ModeContext.setDirty(true);
    }
}

function withSelection(callback) {
    const editable = ensureActiveEditable();
    editable.focus();
    restoreSelection();
    callback();
    captureSelectionSnapshot();
    syncModeContextContent();
}

function runExecCommand(command, value = null) {
    withSelection(() => {
        const succeeded = document.execCommand(command, false, value);
        if (!succeeded) {
            console.warn(`execCommand(${command}) returned false`);
        }
    });
}

function findAncestorMatching(node, predicate, stopNode) {
    let current = node instanceof Node ? node : null;
    while (current && current !== stopNode) {
        if (predicate(current)) {
            return current;
        }
        current = current.parentNode;
    }
    return null;
}

function unwrapNode(node) {
    if (!node || !node.parentNode) {
        return;
    }
    const parent = node.parentNode;
    while (node.firstChild) {
        parent.insertBefore(node.firstChild, node);
    }
    parent.removeChild(node);
}

function getCurrentRange() {
    const selection = document.getSelection();
    if (!selection || selection.rangeCount === 0) {
        return null;
    }
    return selection.getRangeAt(0);
}

function getCurrentBlockTag() {
    const editable = getActiveEditable();
    if (!editable) {
        return null;
    }
    const range = getCurrentRange();
    if (!range) {
        return null;
    }
    const ancestor = findAncestorMatching(
        range.startContainer,
        (node) => node.nodeType === Node.ELEMENT_NODE && /^(P|H[1-6]|BLOCKQUOTE|LI|DIV)$/i.test(node.nodeName),
        editable.parentElement
    );
    return ancestor ? ancestor.nodeName.toUpperCase() : null;
}

function toggleInlineElement(tagName) {
    const editable = getActiveEditable();
    if (!editable) {
        return;
    }
    const selection = document.getSelection();
    if (!selection || selection.rangeCount === 0) {
        return;
    }
    const range = selection.getRangeAt(0);
    const normalizedTag = String(tagName).toUpperCase();
    const existingWrapper = findAncestorMatching(
        range.startContainer,
        (node) => node.nodeName === normalizedTag,
        editable.parentElement
    );

    if (existingWrapper) {
        const newRange = document.createRange();
        newRange.selectNode(existingWrapper);
        unwrapNode(existingWrapper);
        selection.removeAllRanges();
        selection.addRange(newRange);
        return;
    }

    const extracted = range.extractContents();
    const element = document.createElement(tagName);
    if (!extracted || extracted.childNodes.length === 0) {
        element.textContent = '\u200b';
    } else {
        element.appendChild(extracted);
    }
    range.insertNode(element);
    range.selectNodeContents(element);
    selection.removeAllRanges();
    selection.addRange(range);
}

export function toggleBold() {
    withSelection(() => toggleInlineElement('strong'));
}

export function toggleItalic() {
    withSelection(() => toggleInlineElement('em'));
}

export function toggleUnderline() {
    withSelection(() => toggleInlineElement('u'));
}

export function toggleInlineCode() {
    withSelection(() => toggleInlineElement('code'));
}

export function toggleBlockQuote() {
    withSelection(() => {
        const blockTag = getCurrentBlockTag();
        const value = blockTag === 'BLOCKQUOTE' ? 'p' : 'blockquote';
        const succeeded = document.execCommand('formatBlock', false, value);
        if (!succeeded) {
            console.warn('execCommand(formatBlock) failed for blockquote toggle');
        }
    });
}

export function toggleHeading(level) {
    if (!level) {
        throw new Error('Heading level is required');
    }
    withSelection(() => {
        const targetTag = String(level).toUpperCase();
        const blockTag = getCurrentBlockTag();
        const value = blockTag === targetTag ? 'p' : targetTag;
        const succeeded = document.execCommand('formatBlock', false, value);
        if (!succeeded) {
            console.warn(`execCommand(formatBlock) failed for heading ${targetTag}`);
        }
    });
}

export function toggleBulletList() {
    runExecCommand('insertUnorderedList');
}

export function toggleOrderedList() {
    runExecCommand('insertOrderedList');
}

export function getActiveBlockTag() {
    return getCurrentBlockTag();
}
