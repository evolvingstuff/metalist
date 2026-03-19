import { ModeContextInstance as ModeContext } from '../mode-context.js';
import * as Logger from '../mode-logger.js';
import { NotesAPI } from '../../api-client.js';
import { DOMUtils } from '../../dom-utils.js';
import { CONFIG } from '../../config.js';
import { detachEditorSurface } from '../../editor-toolbar.js';
import { clearTagBar, getTagBarValue } from '../services/tag-bar-service.js';
import { scrollWindowToYFastAnimated } from '../services/animated-scroll-service.js';
import { scrollNoteIntoView } from '../services/scroll-restoration-service.js';
import { actionSaveNote } from './content-actions.js';
import { actionSwitchNotes, actionSelectNote } from './selection-actions.js';
import { actionRefreshAndMaybeSelect } from './ui-actions.js';

function getFirstTextNode(fragment) {
    const walker = document.createTreeWalker(fragment, NodeFilter.SHOW_TEXT, null);
    return walker.nextNode();
}

function getLastTextNode(fragment) {
    const walker = document.createTreeWalker(fragment, NodeFilter.SHOW_TEXT, null);
    let lastNode = null;
    let currentNode = walker.nextNode();
    while (currentNode) {
        lastNode = currentNode;
        currentNode = walker.nextNode();
    }
    return lastNode;
}

function isWhitespaceOnlyTextNode(node) {
    if (!(node instanceof Text)) {
        return false;
    }
    const normalized = node.data.replace(/\u00A0/g, ' ');
    return normalized.trim().length === 0;
}

function hasNonTextRenderableContent(element) {
    if (!(element instanceof HTMLElement)) {
        return false;
    }
    return Boolean(
        element.querySelector('img,video,audio,iframe,svg,math,canvas,input,textarea,button,table,hr')
    );
}

function isVisuallyEmptyElement(node) {
    if (!(node instanceof HTMLElement)) {
        return false;
    }
    const tagName = node.tagName.toLowerCase();
    if (tagName === 'br') {
        return true;
    }
    if (hasNonTextRenderableContent(node)) {
        return false;
    }
    const normalizedText = node.textContent ? node.textContent.replace(/\u00A0/g, ' ') : '';
    return normalizedText.trim().length === 0;
}

function stripEdgeEmptyNodes(fragment) {
    while (fragment.firstChild) {
        const firstChild = fragment.firstChild;
        if (isWhitespaceOnlyTextNode(firstChild) || isVisuallyEmptyElement(firstChild)) {
            fragment.removeChild(firstChild);
            continue;
        }
        break;
    }

    while (fragment.lastChild) {
        const lastChild = fragment.lastChild;
        if (isWhitespaceOnlyTextNode(lastChild) || isVisuallyEmptyElement(lastChild)) {
            fragment.removeChild(lastChild);
            continue;
        }
        break;
    }
}

function trimLeadingWhitespaceFromFragment(fragment) {
    while (true) {
        const firstTextNode = getFirstTextNode(fragment);
        if (!firstTextNode) {
            return;
        }
        const trimmed = firstTextNode.data.replace(/^\s+/, '');
        if (trimmed.length === 0) {
            const parentNode = firstTextNode.parentNode;
            if (!parentNode) {
                throw new Error('Text node missing parent during leading-trim');
            }
            parentNode.removeChild(firstTextNode);
            continue;
        }
        firstTextNode.data = trimmed;
        return;
    }
}

function trimTrailingWhitespaceFromFragment(fragment) {
    while (true) {
        const lastTextNode = getLastTextNode(fragment);
        if (!lastTextNode) {
            return;
        }
        const trimmed = lastTextNode.data.replace(/\s+$/, '');
        if (trimmed.length === 0) {
            const parentNode = lastTextNode.parentNode;
            if (!parentNode) {
                throw new Error('Text node missing parent during trailing-trim');
            }
            parentNode.removeChild(lastTextNode);
            continue;
        }
        lastTextNode.data = trimmed;
        return;
    }
}

function fragmentToHtml(fragment) {
    const container = document.createElement('div');
    container.appendChild(fragment);
    return container.innerHTML;
}

function normalizeRangeToSplitSegment(range) {
    if (!(range instanceof Range)) {
        throw new Error('normalizeRangeToSplitSegment requires Range');
    }

    const fragment = range.cloneContents();
    stripEdgeEmptyNodes(fragment);
    trimLeadingWhitespaceFromFragment(fragment);
    trimTrailingWhitespaceFromFragment(fragment);

    const text = typeof fragment.textContent === 'string' ? fragment.textContent : '';
    const html = fragmentToHtml(fragment);
    return {
        html,
        hasText: text.trim().length > 0,
    };
}

function buildSplitSegmentsFromSelection(contentElement) {
    if (!(contentElement instanceof HTMLElement)) {
        throw new Error('buildSplitSegmentsFromSelection requires content element');
    }

    const selection = window.getSelection();
    if (!selection) {
        throw new Error('Selection API unavailable while splitting note');
    }
    if (selection.rangeCount === 0) {
        return [];
    }

    const range = selection.getRangeAt(0);
    if (!contentElement.contains(range.startContainer) || !contentElement.contains(range.endContainer)) {
        return [];
    }

    const beforeRange = document.createRange();
    beforeRange.selectNodeContents(contentElement);
    beforeRange.setEnd(range.startContainer, range.startOffset);

    const afterRange = document.createRange();
    afterRange.selectNodeContents(contentElement);
    afterRange.setStart(range.endContainer, range.endOffset);

    const candidateRanges = range.collapsed
        ? [beforeRange, afterRange]
        : [beforeRange, range.cloneRange(), afterRange];

    const segments = [];
    for (const candidateRange of candidateRanges) {
        const normalized = normalizeRangeToSplitSegment(candidateRange);
        if (!normalized.hasText) {
            continue;
        }
        segments.push(normalized.html);
    }

    return segments;
}

export async function toggleTodoDone(noteId) {
    const startedAt = performance.now();
    Logger.logAction('toggleTodoDone', {
        noteId,
        isEditing: ModeContext.isEditing,
        currentNoteId: ModeContext.currentNoteId,
        isLoading: ModeContext.isLoading
    });

    if (!noteId) {
        throw new Error('Cannot toggle todo/done: noteId is required');
    }

    if (ModeContext.isEditing) {
        throw new Error(`toggleTodoDone called while editing note ${ModeContext.currentNoteId}`);
    }

    await NotesAPI.toggleTodo(noteId);
    await actionRefreshAndMaybeSelect({ startedAt, context: 'toggleTodoDone' });
}

export async function runShellNote(noteId, timeoutSeconds) {
    Logger.logAction('runShellNote', {
        noteId,
        isEditing: ModeContext.isEditing,
        currentNoteId: ModeContext.currentNoteId,
        isLoading: ModeContext.isLoading
    });

    if (!noteId) {
        throw new Error('Cannot run shell: noteId is required');
    }

    if (ModeContext.isEditing) {
        throw new Error(`runShellNote called while editing note ${ModeContext.currentNoteId}`);
    }

    return NotesAPI.runShell(noteId, timeoutSeconds);
}

export async function getShellRun(noteId, runId) {
    if (!noteId) {
        throw new Error('Cannot get shell run: noteId is required');
    }
    if (!runId) {
        throw new Error('Cannot get shell run: runId is required');
    }

    return NotesAPI.getShellRun(noteId, runId);
}

export async function sendShellInput(noteId, runId, text, appendNewline) {
    if (!noteId) {
        throw new Error('Cannot send shell input: noteId is required');
    }
    if (!runId) {
        throw new Error('Cannot send shell input: runId is required');
    }
    if (typeof text !== 'string') {
        throw new Error('Cannot send shell input: text must be a string');
    }
    if (typeof appendNewline !== 'boolean') {
        throw new Error('Cannot send shell input: appendNewline must be a boolean');
    }

    return NotesAPI.sendShellInput(noteId, runId, text, appendNewline);
}

export async function deleteNote(noteId) {
    let startedAt = performance.now();

    let t1 = performance.now();

    Logger.logAction('deleteNote', {
        noteId,
        isEditing: ModeContext.isEditing,
        currentNoteId: ModeContext.currentNoteId
    });

    if (!noteId) {
        throw new Error('Cannot delete note: noteId is required');
    }

    if (ModeContext.currentNoteId !== noteId) {
        throw new Error(`Programming error: Deleting note ${noteId}, but currentNoteId is ${ModeContext.currentNoteId}`);
    }

    if (!ModeContext.isEditing) {
        throw new Error(`Programming error: Deleting current note ${noteId}, but isEditing is false`);
    }

    ModeContext.setEditing(false);
    ModeContext.setCurrentNoteId(null);

    if (ModeContext.currentContent !== null) {
        ModeContext.setCurrentContent(null);
    }
        
	    if (ModeContext.isDirty) {
	        ModeContext.setDirty(false);
	    }

	    let t2 = performance.now();

	    await NotesAPI.deleteNote(noteId);

	    let t3 = performance.now()

    await actionRefreshAndMaybeSelect({startedAt: startedAt, context: 'deleteNote'});

    let t4 = performance.now();
    console.log(`DEBUGZ: deleteNote t2 - t1 ${(t2-t1)} ms`)
    console.log(`DEBUGZ: deleteNote t3 - t2 ${(t3-t2)} ms`)
    console.log(`DEBUGZ: deleteNote t4 - t3 ${(t4-t3)} ms`)
    console.log(`DEBUGZ: deleteNote t4 - t1 ${(t4-t1)} ms`)
}

export async function deleteNoteOutsideEdit(noteId) {
    let startedAt = performance.now();

    Logger.logAction('deleteNoteOutsideEdit', {
        noteId,
        isEditing: ModeContext.isEditing,
        currentNoteId: ModeContext.currentNoteId,
        isLoading: ModeContext.isLoading
    });

    if (!noteId) {
        throw new Error('Cannot delete note: noteId is required');
    }

    if (ModeContext.isEditing) {
        throw new Error(`Programming error: deleteNoteOutsideEdit called while editing note ${ModeContext.currentNoteId}`);
    }

		await NotesAPI.deleteNote(noteId);

		if (ModeContext.currentNoteId === noteId) {
			ModeContext.setCurrentNoteId(null);
		}

		if (ModeContext.currentContent !== null) {
			ModeContext.setCurrentContent(null);
		}

			await actionRefreshAndMaybeSelect({ startedAt: startedAt, context: 'deleteNoteOutsideEdit'});
	}

export async function createNote() {
    const currentNoteId = ModeContext.isEditing ? ModeContext.currentNoteId : null;
    return await createNoteWithPlacement(currentNoteId === null);
}

export async function createNoteAtTop() {
    return await createNoteWithPlacement(true);
}

async function createNoteWithPlacement(placeAtTop) {
    if (typeof placeAtTop !== 'boolean') {
        throw new Error('createNoteWithPlacement requires boolean placeAtTop');
    }

    Logger.logAction('createNote', {
        currentNoteId: ModeContext.currentNoteId,
        isEditing: ModeContext.isEditing,
        isDirty: ModeContext.isDirty,
        placeAtTop,
    });

    const currentNoteId = ModeContext.isEditing ? ModeContext.currentNoteId : null;

    if (ModeContext.isEditing && ModeContext.isDirty && currentNoteId) {
        await actionSaveNote(currentNoteId);
    }

    let data;
    if (!placeAtTop && currentNoteId) {
        Logger.logDebug('Creating new sibling note after note', {
            currentNoteId,
            searchQuery: ModeContext.searchQuery,
        }, Logger.LogCategory.DEBUG);
        data = await NotesAPI.createSibling(currentNoteId, ModeContext.searchQuery);
    } else {
        const firstVisibleNote = document.querySelector('.note');
        const firstVisibleNoteId = firstVisibleNote ? firstVisibleNote.dataset.noteId : '';

        Logger.logDebug('Creating new note at top of list', {
            firstVisibleNoteId,
            searchQuery: ModeContext.searchQuery,
        }, Logger.LogCategory.DEBUG);
        data = await NotesAPI.createNote(firstVisibleNoteId, ModeContext.searchQuery);
    }

    const newNoteId = data.id;
    const caretOptions = { initialCaretVisibility: 'visible' };
    if (ModeContext.isEditing) {
        await actionSwitchNotes(newNoteId, caretOptions);
    } else {
        await actionSelectNote(newNoteId, caretOptions);
    }

    if (placeAtTop) {
        scrollWindowToYFastAnimated(0);
    }

    return newNoteId;
}

export async function createChildNote() {
    let startedAt = performance.now();

    Logger.logAction('createChildNote', {
        currentNoteId: ModeContext.currentNoteId,
        isEditing: ModeContext.isEditing,
        isDirty: ModeContext.isDirty
    });

    const currentNoteId = ModeContext.currentNoteId;

    if (!currentNoteId) {
        Logger.logDebug('Cannot create child note: no parent note selected', {}, Logger.LogCategory.DEBUG);
        return await createNote();
    }

    if (ModeContext.isEditing && ModeContext.isDirty && currentNoteId) {
        await actionSaveNote(currentNoteId);
    }

	    Logger.logDebug('Creating new child note under parent', { 
        parentNoteId: currentNoteId 
    }, Logger.LogCategory.DEBUG);
    
    const data = await NotesAPI.createChild(currentNoteId, ModeContext.searchQuery);
    const newNoteId = data.id;

	    const caretOptions = { initialCaretVisibility: 'visible' };
    if (ModeContext.isEditing) {
        return await actionSwitchNotes(newNoteId, caretOptions);
    } else {
        return await actionSelectNote(newNoteId, caretOptions);
    }
}

export async function moveNoteUp(noteId) {
    let startedAt = performance.now();

    Logger.logAction('moveNoteUp', {
        noteId,
        isEditing: ModeContext.isEditing,
        currentNoteId: ModeContext.currentNoteId,
        isDirty: ModeContext.isDirty
    });

    if (!noteId) {
        throw new Error('Cannot move note: noteId is required');
    }

    if (ModeContext.isDirty && noteId === ModeContext.currentNoteId) {
        await actionSaveNote(noteId);
    }

		await NotesAPI.moveNoteUp(noteId);

    if (ModeContext.isEditing) {
        ModeContext.markCaretHidden();
    }

    const newContent = await actionRefreshAndMaybeSelect({startedAt: startedAt, context: 'moveNoteUp'});

    if (ModeContext.currentContent !== newContent) {
        ModeContext.setCurrentContent(newContent);
    }
}

export async function moveNoteDown(noteId) {
    let startedAt = performance.now();

    Logger.logAction('moveNoteDown', {
        noteId,
        isEditing: ModeContext.isEditing,
        currentNoteId: ModeContext.currentNoteId,
        isDirty: ModeContext.isDirty
    });

    if (!noteId) {
        throw new Error('Cannot move note: noteId is required');
    }

    if (ModeContext.isDirty && noteId === ModeContext.currentNoteId) {
        await actionSaveNote(noteId);
    }

		await NotesAPI.moveNoteDown(noteId);

    if (ModeContext.isEditing) {
        ModeContext.markCaretHidden();
    }

    const newContent = await actionRefreshAndMaybeSelect({startedAt: startedAt, context: 'moveNoteDown'});

    if (ModeContext.currentContent !== newContent) {
        ModeContext.setCurrentContent(newContent);
    }
}

export async function indentNote(noteId) {
    let startedAt = performance.now();

    Logger.logAction('indentNote', {
        noteId,
        isEditing: ModeContext.isEditing,
        currentNoteId: ModeContext.currentNoteId,
        isDirty: ModeContext.isDirty
    });

    if (!noteId) {
        throw new Error('Cannot indent note: noteId is required');
    }

    const noteElement = DOMUtils.getNoteById(noteId);
    let prevElement = noteElement.previousElementSibling;
    while (prevElement && !prevElement.classList.contains(CONFIG.CLASSES.NOTE)) {
        prevElement = prevElement.previousElementSibling;
    }
    if (!prevElement) {
        Logger.logNoop('Indent shortcut ignored: no visible sibling above', {
            noteId,
            isEditing: ModeContext.isEditing
        });
        return;
    }
    const visiblePrevId = DOMUtils.getNoteId(prevElement);
    if (typeof visiblePrevId !== 'string' || visiblePrevId.length === 0) {
        throw new Error('Visible previous sibling missing note id');
    }

    if (ModeContext.isDirty && noteId === ModeContext.currentNoteId) {
        await actionSaveNote(noteId);
    }

    await NotesAPI.indentNote(noteId, visiblePrevId);

    if (ModeContext.isEditing) {
        ModeContext.markCaretHidden();
    }

    const newContent = await actionRefreshAndMaybeSelect({startedAt: startedAt, context: 'indentNote'});

    if (ModeContext.currentContent !== newContent) {
        ModeContext.setCurrentContent(newContent);
    }
}

export async function outdentNote(noteId) {
    let startedAt = performance.now();

    Logger.logAction('outdentNote', {
        noteId,
        isEditing: ModeContext.isEditing,
        currentNoteId: ModeContext.currentNoteId,
        isDirty: ModeContext.isDirty
    });

    if (!noteId) {
        throw new Error('Cannot outdent note: noteId is required');
    }

    if (ModeContext.isDirty && noteId === ModeContext.currentNoteId) {
        await actionSaveNote(noteId);
    }

    await NotesAPI.outdentNote(noteId, ModeContext.searchQuery);

    if (ModeContext.isEditing) {
        ModeContext.markCaretHidden();
    }

    const newContent = await actionRefreshAndMaybeSelect({startedAt: startedAt, context: 'outdentNote'});

    if (ModeContext.currentContent !== newContent) {
        ModeContext.setCurrentContent(newContent);
    }
}

async function setNoteCollapse(noteId, collapsed) {
    let startedAt = performance.now();

    Logger.logAction('setNoteCollapse', {
        noteId,
        collapsed,
        isEditing: ModeContext.isEditing,
        hoveredNoteId: ModeContext.hoveredNoteId
    });

    if (!noteId) {
        throw new Error('Cannot change collapse state: noteId is required');
    }

	    if (ModeContext.isEditing) {
        const editingNoteId = ModeContext.currentNoteId;
        if (!editingNoteId) {
            throw new Error('Invariant violation: isEditing is true but currentNoteId is null');
        }

        Logger.logDebug('Collapse toggle clicked while editing; exiting edit mode first', {
            editingNoteId,
            targetNoteId: noteId,
            collapsed
        }, Logger.LogCategory.EVENT);

        if (ModeContext.isDirty) {
            await actionSaveNote(editingNoteId);
        }

        const editingNoteElement = DOMUtils.getNoteById(editingNoteId);
        DOMUtils.setNoteEditable(editingNoteElement, false);
        DOMUtils.revealCaret(editingNoteElement);
        detachEditorSurface();
        clearTagBar();

        ModeContext.setEditing(false);
        ModeContext.setCurrentNoteId(null);
        if (ModeContext.currentContent !== null) {
            ModeContext.setCurrentContent(null);
        }
    }

	    if (collapsed) {
	        await NotesAPI.collapseNote(noteId);
	    } else {
	        await NotesAPI.expandNote(noteId);
	    }
	    await actionRefreshAndMaybeSelect({ startedAt: startedAt, context: 'setNoteCollapse' });
}

export async function collapseNote(noteId) {
    await setNoteCollapse(noteId, true);
}

export async function expandNote(noteId) {
    await setNoteCollapse(noteId, false);
}

export async function actionCopyNote() {
    ModeContext._requestStartedAt = performance.now();

    const currentNoteId = ModeContext.currentNoteId;
    
    Logger.logAction('actionCopyNote', { 
        currentNoteId,
        isEditing: ModeContext.isEditing,
        isDirty: ModeContext.isDirty
    });

    if (!currentNoteId) {
        throw new Error('Cannot copy note: no note selected');
    }

    // Save the note first if it's dirty to ensure we copy the current edited content
    if (ModeContext.isDirty) {
        await actionSaveNote(currentNoteId);
    }

    // Call the server to serialize the note tree to clipboard
    const response = await NotesAPI.copyNote(currentNoteId);

    // No need to store clipboard state client-side anymore
    return response;
}

export async function splitCurrentNoteFromSelection() {
    const currentNoteId = ModeContext.currentNoteId;
    Logger.logAction('splitCurrentNoteFromSelection', {
        currentNoteId,
        isEditing: ModeContext.isEditing,
        isDirty: ModeContext.isDirty,
    });

    if (!ModeContext.isEditing) {
        Logger.logNoop('Split shortcut ignored: not editing');
        return false;
    }
    if (typeof currentNoteId !== 'string' || currentNoteId.length === 0) {
        Logger.logNoop('Split shortcut ignored: no active note');
        return false;
    }

    const noteElement = DOMUtils.getNoteById(currentNoteId);
    const contentElement = DOMUtils.getNoteContent(noteElement);
    if (!(contentElement instanceof HTMLElement)) {
        throw new Error('Current note missing editable content element for split');
    }

    const splitSegments = buildSplitSegmentsFromSelection(contentElement);
    if (splitSegments.length <= 1) {
        Logger.logNoop('Split shortcut ignored: selection/caret produced no split', {
            segmentCount: splitSegments.length,
        });
        return false;
    }

    const tags = getTagBarValue(noteElement);
    await NotesAPI.saveNote(currentNoteId, splitSegments[0], tags);

    let anchorNoteId = currentNoteId;
    let index = 1;
    while (index < splitSegments.length) {
        const createResponse = await NotesAPI.createSibling(anchorNoteId, ModeContext.searchQuery);
        const createdNoteId = createResponse && typeof createResponse.id === 'string'
            ? createResponse.id
            : '';
        if (createdNoteId.length === 0) {
            throw new Error('Split sibling creation response missing id');
        }

        await NotesAPI.saveNote(createdNoteId, splitSegments[index], tags);
        anchorNoteId = createdNoteId;
        index += 1;
    }

    const startedAt = performance.now();
    const refreshedContent = await actionRefreshAndMaybeSelect({
        startedAt,
        context: 'splitCurrentNoteFromSelection',
    });
    if (typeof refreshedContent === 'string' && ModeContext.currentContent !== refreshedContent) {
        ModeContext.setCurrentContent(refreshedContent);
    }

    if (ModeContext.isDirty) {
        ModeContext.setDirty(false);
    }
    ModeContext.setLastSavedContent(splitSegments[0]);

    return true;
}

export async function joinCurrentNoteWithNextSibling() {
    const currentNoteId = ModeContext.currentNoteId;
    Logger.logAction('joinCurrentNoteWithNextSibling', {
        currentNoteId,
        isEditing: ModeContext.isEditing,
        isDirty: ModeContext.isDirty,
    });

    if (!ModeContext.isEditing) {
        Logger.logNoop('Join shortcut ignored: not editing');
        return false;
    }
    if (typeof currentNoteId !== 'string' || currentNoteId.length === 0) {
        Logger.logNoop('Join shortcut ignored: no active note');
        return false;
    }

    if (ModeContext.isDirty) {
        await actionSaveNote(currentNoteId);
    }

    const response = await NotesAPI.joinNextSibling(currentNoteId);
    if (response && response.status === 'noop') {
        Logger.logNoop('Join shortcut ignored: no joinable next sibling', {
            currentNoteId,
        });
        return false;
    }

    const startedAt = performance.now();
    const refreshedContent = await actionRefreshAndMaybeSelect({
        startedAt,
        context: 'joinCurrentNoteWithNextSibling',
    });
    if (typeof refreshedContent === 'string' && ModeContext.currentContent !== refreshedContent) {
        ModeContext.setCurrentContent(refreshedContent);
        ModeContext.setLastSavedContent(refreshedContent);
    }

    if (ModeContext.isDirty) {
        ModeContext.setDirty(false);
    }

    return true;
}

export async function toggleReferenceModeForNote(hostNoteId, referenceNoteId, occurrenceIndex, mode) {
    const startedAt = performance.now();
    Logger.logAction('toggleReferenceModeForNote', {
        hostNoteId,
        referenceNoteId,
        occurrenceIndex,
        mode,
        isEditing: ModeContext.isEditing,
        currentNoteId: ModeContext.currentNoteId,
    });

    if (typeof hostNoteId !== 'string' || hostNoteId.length === 0) {
        throw new Error('Cannot toggle reference mode: hostNoteId is required');
    }
    if (typeof referenceNoteId !== 'string' || referenceNoteId.length === 0) {
        throw new Error('Cannot toggle reference mode: referenceNoteId is required');
    }
    if (!Number.isInteger(occurrenceIndex) || occurrenceIndex < 0) {
        throw new Error('Cannot toggle reference mode: occurrenceIndex must be a non-negative integer');
    }
    if (mode !== 'embed' && mode !== 'link') {
        throw new Error('Cannot toggle reference mode: mode must be embed|link');
    }
    if (ModeContext.isEditing) {
        throw new Error('toggleReferenceModeForNote must not run while editing');
    }

    await NotesAPI.toggleReferenceMode(hostNoteId, referenceNoteId, occurrenceIndex, mode);
    const refreshedContent = await actionRefreshAndMaybeSelect({
        startedAt,
        context: 'toggleReferenceModeForNote',
    });
    if (typeof refreshedContent === 'string' && ModeContext.currentContent !== refreshedContent) {
        ModeContext.setCurrentContent(refreshedContent);
    }
}

export async function actionPasteNoteSibling() {
    const currentNoteId = ModeContext.currentNoteId;

    Logger.logAction('actionPasteNoteSibling', {
        currentNoteId,
        isEditing: ModeContext.isEditing
    });

    if (!ModeContext.isEditing || !currentNoteId) {
        throw new Error('Cannot paste sibling: no note selected');
    }

    if (ModeContext.isDirty) {
        await actionSaveNote(currentNoteId);
    }

	    const response = await NotesAPI.pasteNoteSibling(currentNoteId);

    const newNoteId = response.id;
    if (typeof newNoteId !== 'string' || newNoteId.length === 0) {
        throw new Error('Paste sibling response missing new note id');
    }

    if (newNoteId === currentNoteId) {
        const startedAt = performance.now();
        const newContent = await actionRefreshAndMaybeSelect({ startedAt, context: 'pasteNoteSiblingInto' });
        if (ModeContext.currentContent !== newContent && newContent !== null) {
            ModeContext.setCurrentContent(newContent);
        }
        window.requestAnimationFrame(() => {
            scrollNoteIntoView(newNoteId, {});
        });
        return;
    }

    await actionSwitchNotes(newNoteId, { initialCaretVisibility: 'hidden' });
    window.requestAnimationFrame(() => {
        scrollNoteIntoView(newNoteId, {});
    });
}

export async function actionPasteNoteChild() {
    const currentNoteId = ModeContext.currentNoteId;
    
    Logger.logAction('actionPasteNoteChild', { 
        currentNoteId,
        isEditing: ModeContext.isEditing
    });

    if (!ModeContext.isEditing || !currentNoteId) {
        throw new Error('Cannot paste child: no note selected');
    }

    if (ModeContext.isDirty) {
        await actionSaveNote(currentNoteId);
    }

	    const response = await NotesAPI.pasteNoteChild(currentNoteId);

    const newNoteId = response.id;
    if (typeof newNoteId !== 'string' || newNoteId.length === 0) {
        throw new Error('Paste child response missing new note id');
    }

    await actionSwitchNotes(newNoteId, { initialCaretVisibility: 'hidden' });
    window.requestAnimationFrame(() => {
        scrollNoteIntoView(newNoteId, {});
    });
}
