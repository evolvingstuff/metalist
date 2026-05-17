import { ModeContextInstance as ModeContext } from '../mode-context.js';
import * as Logger from '../mode-logger.js';
import { actionExitSearchMode } from '../actions/search-actions.js';
import {
    actionSaveAndExitEditingWithoutRefreshing,
    actionSelectNote,
    actionSwitchNotes,
} from '../actions/selection-actions.js';
import { actionSaveNote } from '../actions/content-actions.js';
import {
    createChildNote,
    createNote,
    deleteNote,
    moveNoteToTop,
} from '../actions/note-actions.js';
import { CommandGate } from '../services/command-gate-service.js';
import { prepareMoveNoteToTopContextAction } from '../services/note-context-menu-action-service.js';
import {
    copyImageFromContext,
    openImageInNewTabFromContext,
    resolveImageContextFromElement,
    saveImageFromContext,
    zoomImageFromContext,
} from '../services/image-context-menu-action-service.js';
import { OntologyModal } from '../../modals/ontology-modal.js';
import { findTagAtIndexInTagBar } from '../services/tag-syntax-service.js';
import { findSearchTagAtIndex } from '../services/search-syntax-service.js';
import { getInputCaretIndexFromPoint } from '../../context-menu/input-caret-service.js';
import { buildContextMenuItems } from '../../context-menu/context-menu-registry.js';
import { initContextMenuService, showContextMenu } from '../../context-menu/context-menu-service.js';

const ontologyModal = new OntologyModal();

function resolveEventElement(target) {
    if (target instanceof HTMLElement) {
        return target;
    }
    if (target && target.nodeType === 3 && target.parentElement instanceof HTMLElement) {
        return target.parentElement;
    }
    return null;
}

function resolveTagFromSelection(rawValue, selectionStart, selectionEnd, findTagAtIndex) {
    if (!Number.isInteger(selectionStart) || !Number.isInteger(selectionEnd)) {
        return null;
    }
    if (selectionEnd <= selectionStart) {
        return null;
    }
    const selectionTag = findTagAtIndex(rawValue, selectionStart);
    if (!selectionTag) {
        return null;
    }
    if (selectionEnd <= selectionTag.end) {
        return selectionTag;
    }
    return null;
}

function resolveTagFromInput(event, input, findTagAtIndex) {
    if (!event) {
        throw new Error('resolveTagFromInput called without event');
    }
    if (!(input instanceof HTMLInputElement)) {
        throw new Error('resolveTagFromInput requires input element');
    }
    if (typeof findTagAtIndex !== 'function') {
        throw new Error('resolveTagFromInput requires findTagAtIndex function');
    }

    const rawValue = input.value;
    if (typeof rawValue !== 'string') {
        throw new Error('Input value must be string');
    }

    const selectionStart = input.selectionStart;
    const selectionEnd = input.selectionEnd;
    const selectionTag = resolveTagFromSelection(rawValue, selectionStart, selectionEnd, findTagAtIndex);
    if (selectionTag) {
        return selectionTag;
    }

    if (typeof event.clientX !== 'number' || typeof event.clientY !== 'number') {
        throw new Error('Context menu event missing coordinates');
    }
    const clickIndex = getInputCaretIndexFromPoint(input, event.clientX);
    const clickTag = findTagAtIndex(rawValue, clickIndex);
    if (clickTag) {
        return clickTag;
    }

    if (Number.isInteger(selectionStart)) {
        return findTagAtIndex(rawValue, selectionStart);
    }

    return null;
}

async function openOntologyModalWithFocus(tag) {
    if (typeof tag !== 'string' || tag.trim() === '') {
        throw new Error('openOntologyModalWithFocus requires non-empty tag');
    }

    if (ModeContext.isLoading) {
        return;
    }

    if (Array.isArray(ModeContext.modalStack) && ModeContext.modalStack.length > 0) {
        const topModal = ModeContext.modalStack[ModeContext.modalStack.length - 1];
        if (topModal !== 'ontologyModal') {
            return;
        }
    }

    if (ModeContext.isSearching) {
        actionExitSearchMode();
    }

    if (ModeContext.isEditing) {
        const result = await CommandGate.run('contextMenu.ontology.exit_editing', async () => {
            await actionSaveAndExitEditingWithoutRefreshing();
        });
        if (result === null) {
            return;
        }
    }

    if (ontologyModal.isOpen) {
        await ontologyModal.setFocusTag(tag);
        return;
    }

    ontologyModal.suppressSearchFocusOnce();
    ontologyModal.suppressSearchResultsOnce();
    ontologyModal.open();
    await ontologyModal.setFocusTag(tag);
}

function showTagContextMenu(event, tag, source) {
    if (typeof tag !== 'string' || tag.trim() === '') {
        return;
    }
    if (typeof source !== 'string' || source.trim() === '') {
        throw new Error('showTagContextMenu requires source string');
    }
    if (!event) {
        throw new Error('showTagContextMenu called without event');
    }
    if (typeof event.clientX !== 'number' || typeof event.clientY !== 'number') {
        throw new Error('Context menu event missing coordinates');
    }

    const context = { kind: 'tag', tag, source };
    const items = buildContextMenuItems(context, {
        onEditTagRelationships: (focusTag) => {
            void openOntologyModalWithFocus(focusTag);
        },
    });

    if (!Array.isArray(items) || items.length === 0) {
        return;
    }

    event.preventDefault();
    event.stopPropagation();

    showContextMenu({
        items,
        position: { x: event.clientX, y: event.clientY },
        onClose: null,
    });
}

function resolveContextNoteElement(element) {
    if (!(element instanceof HTMLElement)) {
        return null;
    }

    const noteElement = element.closest('.note');
    if (!(noteElement instanceof HTMLElement)) {
        return null;
    }
    if (noteElement.classList.contains('locked')) {
        return null;
    }
    if (noteElement.classList.contains('search-redacted')) {
        return null;
    }
    const noteId = noteElement.dataset.noteId;
    if (typeof noteId !== 'string' || noteId.trim() === '') {
        throw new Error('Context-menu note element missing data-note-id');
    }
    return noteElement;
}

async function focusNoteForContextAction(noteId) {
    if (typeof noteId !== 'string' || noteId.trim() === '') {
        throw new Error('focusNoteForContextAction requires noteId');
    }

    if (ModeContext.isSearching) {
        actionExitSearchMode();
    }

    if (ModeContext.isEditing) {
        if (ModeContext.currentNoteId === noteId) {
            return;
        }
        await actionSwitchNotes(noteId, { initialCaretVisibility: 'hidden' });
        return;
    }

    await actionSelectNote(noteId, { initialCaretVisibility: 'hidden' });
}

function showNoteContextMenu(event, noteId, imageContext) {
    if (typeof noteId !== 'string' || noteId.trim() === '') {
        return;
    }
    if (!event) {
        throw new Error('showNoteContextMenu called without event');
    }
    if (typeof event.clientX !== 'number' || typeof event.clientY !== 'number') {
        throw new Error('Context menu event missing coordinates');
    }

    const context = { kind: 'note', noteId, imageContext };
    const items = buildContextMenuItems(context, {
        onCopyImage: (targetImageContext) => {
            void CommandGate.run('contextMenu.image.copy', async () => {
                await copyImageFromContext(targetImageContext);
            });
        },
        onSaveImage: (targetImageContext) => {
            void CommandGate.run('contextMenu.image.save', async () => {
                await saveImageFromContext(targetImageContext);
            });
        },
        onZoomImage: (targetImageContext) => {
            void CommandGate.run('contextMenu.image.zoom', async () => {
                await zoomImageFromContext(targetImageContext);
            });
        },
        onOpenImageInNewTab: (targetImageContext) => {
            void CommandGate.run('contextMenu.image.open_new_tab', async () => {
                await openImageInNewTabFromContext(targetImageContext);
            });
        },
        onAddSiblingNote: (targetNoteId) => {
            void CommandGate.run('contextMenu.note.add_sibling', async () => {
                await focusNoteForContextAction(targetNoteId);
                await createNote();
            });
        },
        onAddChildNote: (targetNoteId) => {
            void CommandGate.run('contextMenu.note.add_child', async () => {
                await focusNoteForContextAction(targetNoteId);
                await createChildNote();
            });
        },
        onDeleteNote: (targetNoteId) => {
            void CommandGate.run('contextMenu.note.delete', async () => {
                await focusNoteForContextAction(targetNoteId);
                await deleteNote(targetNoteId);
            });
        },
        onMoveNoteToTop: (targetNoteId) => {
            void CommandGate.run('contextMenu.note.move_to_top', async () => {
                await prepareMoveNoteToTopContextAction({
                    targetNoteId,
                    modeContext: ModeContext,
                    exitSearchModeFn: actionExitSearchMode,
                    saveActiveNoteFn: actionSaveNote,
                });
                await moveNoteToTop(targetNoteId);
            });
        },
    });

    if (!Array.isArray(items) || items.length === 0) {
        return;
    }

    event.preventDefault();
    event.stopPropagation();

    showContextMenu({
        items,
        position: { x: event.clientX, y: event.clientY },
        onClose: null,
    });
}

function handleContextMenu(event) {
    if (!event) {
        throw new Error('handleContextMenu called without event');
    }
    if (ModeContext.isLoading) {
        return;
    }

    const element = resolveEventElement(event.target);
    if (!element) {
        return;
    }

    const tagBarInput = element.closest('.note-tag-bar-input');
    if (tagBarInput) {
        const tagInfo = resolveTagFromInput(event, tagBarInput, findTagAtIndexInTagBar);
        if (tagInfo && typeof tagInfo.text === 'string') {
            showTagContextMenu(event, tagInfo.text, 'tag-bar');
            return;
        }
    }

    const searchInput = element.closest('#search-input');
    if (searchInput) {
        const tagInfo = resolveTagFromInput(event, searchInput, findSearchTagAtIndex);
        if (tagInfo && typeof tagInfo.tag === 'string') {
            showTagContextMenu(event, tagInfo.tag, 'search');
        }
        return;
    }

    const noteElement = resolveContextNoteElement(element);
    if (noteElement) {
        const imageContext = resolveImageContextFromElement(element);
        showNoteContextMenu(event, noteElement.dataset.noteId, imageContext);
    }
}

export function initContextMenuEvents() {
    initContextMenuService();
    document.addEventListener('contextmenu', handleContextMenu, { capture: true });
    Logger.logInit('Context menu events handler');
}
