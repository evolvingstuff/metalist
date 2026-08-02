import { getTagBarValue, setTagBarValue } from './tag-bar-service.js';
import { buildSelectedFormattingRemovalPlan } from './remove-formatting-service.js';

function textLengthForRange(range) {
    if (!(range instanceof Range)) {
        throw new Error('textLengthForRange requires Range');
    }
    const container = document.createElement('div');
    container.appendChild(range.cloneContents());
    const text = container.textContent;
    return typeof text === 'string' ? text.length : 0;
}

function resolveSelectionOffsets(noteContent, selectedRange) {
    if (!(noteContent instanceof HTMLElement)) {
        throw new Error('resolveSelectionOffsets requires note content element');
    }
    if (!(selectedRange instanceof Range) || selectedRange.collapsed) {
        throw new Error('resolveSelectionOffsets requires non-collapsed Range');
    }
    if (!noteContent.contains(selectedRange.startContainer) || !noteContent.contains(selectedRange.endContainer)) {
        throw new Error('Selected formatting range must stay inside note content');
    }

    const beforeRange = document.createRange();
    beforeRange.selectNodeContents(noteContent);
    beforeRange.setEnd(selectedRange.startContainer, selectedRange.startOffset);
    const selectionStart = textLengthForRange(beforeRange);
    const selectionLength = textLengthForRange(selectedRange);
    return {
        selectionStart,
        selectionEnd: selectionStart + selectionLength,
    };
}

function resolveTextBoundary(noteContent, textOffset) {
    if (!(noteContent instanceof HTMLElement)) {
        throw new Error('resolveTextBoundary requires note content element');
    }
    if (!Number.isInteger(textOffset) || textOffset < 0) {
        throw new Error('resolveTextBoundary requires non-negative integer offset');
    }

    const walker = document.createTreeWalker(noteContent, NodeFilter.SHOW_TEXT);
    let consumed = 0;
    let textNode = walker.nextNode();
    while (textNode) {
        const length = textNode.data.length;
        if (textOffset <= consumed + length) {
            return { node: textNode, offset: textOffset - consumed };
        }
        consumed += length;
        textNode = walker.nextNode();
    }
    if (textOffset !== consumed) {
        throw new Error(`Text offset ${textOffset} exceeds note content length ${consumed}`);
    }
    return { node: noteContent, offset: noteContent.childNodes.length };
}

function deleteTextRange(noteContent, start, end) {
    const startBoundary = resolveTextBoundary(noteContent, start);
    const endBoundary = resolveTextBoundary(noteContent, end);
    const range = document.createRange();
    range.setStart(startBoundary.node, startBoundary.offset);
    range.setEnd(endBoundary.node, endBoundary.offset);
    range.deleteContents();
}

function adjustedInsertionPosition(position, removals) {
    let removedBefore = 0;
    for (const removal of removals) {
        if (removal.start < position && position < removal.end) {
            throw new Error('Formatting insertion cannot land inside a removed delimiter');
        }
        if (removal.end <= position) {
            removedBefore += removal.end - removal.start;
        }
    }
    return position - removedBefore;
}

function applyDelimiterEdits(noteContent, plan) {
    const descendingRemovals = [...plan.removals].sort((left, right) => right.start - left.start);
    for (const removal of descendingRemovals) {
        deleteTextRange(noteContent, removal.start, removal.end);
    }

    const adjustedInsertions = new Map();
    for (const insertion of plan.insertions) {
        const position = adjustedInsertionPosition(insertion.position, plan.removals);
        const existing = adjustedInsertions.has(position)
            ? adjustedInsertions.get(position)
            : '';
        adjustedInsertions.set(position, `${existing}${insertion.text}`);
    }
    const descendingInsertions = [...adjustedInsertions.entries()].sort(
        ([leftPosition], [rightPosition]) => rightPosition - leftPosition,
    );
    for (const [position, text] of descendingInsertions) {
        const boundary = resolveTextBoundary(noteContent, position);
        const range = document.createRange();
        range.setStart(boundary.node, boundary.offset);
        range.collapse(true);
        range.insertNode(document.createTextNode(text));
    }
}

export function restoreFormattingRemovalSelection(noteContent, selectionStart, selectionEnd) {
    if (!(noteContent instanceof HTMLElement)) {
        throw new Error('restoreFormattingRemovalSelection requires note content element');
    }
    const startBoundary = resolveTextBoundary(noteContent, selectionStart);
    const endBoundary = resolveTextBoundary(noteContent, selectionEnd);
    const range = document.createRange();
    range.setStart(startBoundary.node, startBoundary.offset);
    range.setEnd(endBoundary.node, endBoundary.offset);

    noteContent.focus();
    const selection = window.getSelection();
    if (!selection) {
        throw new Error('Selection API unavailable after Remove Formatting');
    }
    selection.removeAllRanges();
    selection.addRange(range);
    return range.cloneRange();
}

export function resolveActiveFormattingRemovalRange(noteContent) {
    if (!(noteContent instanceof HTMLElement)) {
        throw new Error('resolveActiveFormattingRemovalRange requires note content element');
    }
    const selection = window.getSelection();
    if (!selection || selection.rangeCount === 0) {
        return null;
    }
    const range = selection.getRangeAt(0);
    if (range.collapsed) {
        return null;
    }
    if (!noteContent.contains(range.startContainer) || !noteContent.contains(range.endContainer)) {
        return null;
    }
    const offsets = resolveSelectionOffsets(noteContent, range);
    if (offsets.selectionEnd <= offsets.selectionStart) {
        return null;
    }
    return range.cloneRange();
}

export function removeFormattingFromSelectedRange(noteElement, noteContent, selectedRange) {
    if (!(noteElement instanceof HTMLElement)) {
        throw new Error('removeFormattingFromSelectedRange requires note element');
    }
    if (!(noteContent instanceof HTMLElement)) {
        throw new Error('removeFormattingFromSelectedRange requires note content element');
    }
    if (!(selectedRange instanceof Range) || selectedRange.collapsed) {
        throw new Error('removeFormattingFromSelectedRange requires non-collapsed Range');
    }

    const offsets = resolveSelectionOffsets(noteContent, selectedRange);
    const contentText = noteContent.textContent;
    if (typeof contentText !== 'string') {
        throw new Error('Remove Formatting note content text is unavailable');
    }
    const originalTags = getTagBarValue(noteElement);
    const plan = buildSelectedFormattingRemovalPlan({
        contentText,
        tagBarText: originalTags,
        selectionStart: offsets.selectionStart,
        selectionEnd: offsets.selectionEnd,
    });

    const selection = window.getSelection();
    if (!selection) {
        throw new Error('Selection API unavailable before Remove Formatting');
    }
    selection.removeAllRanges();
    selection.addRange(selectedRange.cloneRange());

    const originalHtml = noteContent.innerHTML;
    if (typeof document.execCommand !== 'function') {
        throw new Error('Browser removeFormat command is unavailable');
    }
    document.execCommand('removeFormat', false, null);
    applyDelimiterEdits(noteContent, plan);
    setTagBarValue(noteElement, plan.tagBarText);

    if (noteContent.textContent !== plan.contentText) {
        throw new Error('Remove Formatting delimiter edits diverged from the removal plan');
    }
    let changed = noteContent.innerHTML !== originalHtml;
    if (plan.tagBarText !== originalTags) {
        changed = true;
    }
    restoreFormattingRemovalSelection(
        noteContent,
        plan.selectionStart,
        plan.selectionEnd,
    );
    return {
        changed,
        selectionStart: plan.selectionStart,
        selectionEnd: plan.selectionEnd,
    };
}
