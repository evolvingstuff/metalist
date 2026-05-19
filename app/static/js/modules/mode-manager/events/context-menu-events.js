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
    actionCopyNoteById,
    actionPasteNoteChild,
    actionPasteNoteSibling,
    createChildNote,
    createNote,
    deleteNote,
    moveNoteToTop,
} from '../actions/note-actions.js';
import { CommandGate } from '../services/command-gate-service.js';
import { prepareMoveNoteToTopContextAction } from '../services/note-context-menu-action-service.js';
import { writeRenderedNoteToSystemClipboard } from '../services/note-clipboard-write-service.js';
import { insertReferenceTokenIntoActiveEditor } from '../services/file-reference-service.js';
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
import { CommandPalette } from '../../command-palette/command-palette-controller.js';

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
        const topModal = ModeContext.topModal;
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

function showPreferenceContextMenu(event, itemId, itemLabel, preferenceKey, nextValue) {
    if (!event) {
        throw new Error('showPreferenceContextMenu called without event');
    }
    if (typeof event.clientX !== 'number' || typeof event.clientY !== 'number') {
        throw new Error('Context menu event missing coordinates');
    }
    if (typeof itemId !== 'string' || itemId.trim() === '') {
        throw new Error('showPreferenceContextMenu requires itemId');
    }
    if (typeof itemLabel !== 'string' || itemLabel.trim() === '') {
        throw new Error('showPreferenceContextMenu requires itemLabel');
    }
    if (typeof preferenceKey !== 'string' || preferenceKey.trim() === '') {
        throw new Error('showPreferenceContextMenu requires preferenceKey');
    }
    if (typeof nextValue !== 'boolean') {
        throw new Error('showPreferenceContextMenu requires boolean nextValue');
    }

    event.preventDefault();
    event.stopPropagation();

    showContextMenu({
        items: [
            {
                id: itemId,
                label: itemLabel,
                enabled: true,
                onSelect: () => {
                    void CommandPalette.applyPreference(preferenceKey, nextValue);
                },
            },
        ],
        position: { x: event.clientX, y: event.clientY },
        onClose: null,
    });
}

function showCalendarRailContextMenu(event) {
    const isCalendarVisible = document.body.classList.contains('pref-show-rhs-panel');
    const itemLabel = isCalendarVisible ? 'Hide Calendar View' : 'Show Calendar View';
    showPreferenceContextMenu(
        event,
        'toggle-calendar-view',
        itemLabel,
        'pref.show_rhs_panel',
        !isCalendarVisible,
    );
}

function showTabsRailContextMenu(event) {
    const areTabsVisible = document.body.classList.contains('pref-show-tab-ui');
    const itemLabel = areTabsVisible ? 'Hide Tabs' : 'Show Tabs';
    showPreferenceContextMenu(
        event,
        'toggle-tabs',
        itemLabel,
        'pref.show_tab_ui',
        !areTabsVisible,
    );
}

function readCssPixelVariable(name) {
    if (typeof name !== 'string' || name.trim() === '') {
        throw new Error('readCssPixelVariable requires name');
    }
    const rawValue = window.getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    const parsed = Number.parseFloat(rawValue);
    if (!Number.isFinite(parsed) || parsed < 0) {
        throw new Error(`CSS variable ${name} must be a non-negative pixel value`);
    }
    return parsed;
}

function isInRightRail(event) {
    if (typeof event.clientX !== 'number') {
        throw new Error('Context menu event missing clientX');
    }
    const edge = readCssPixelVariable('--side-rail-edge');
    const width = readCssPixelVariable('--side-rail-width');
    return event.clientX >= window.innerWidth - edge - width;
}

function isInLeftTabRail(event) {
    if (typeof event.clientX !== 'number') {
        throw new Error('Context menu event missing clientX');
    }
    const edge = readCssPixelVariable('--side-rail-edge');
    const width = readCssPixelVariable('--side-rail-width');
    return event.clientX <= edge + width;
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

function resolveSelectedTextRangeForNote(noteElement) {
    if (!(noteElement instanceof HTMLElement)) {
        throw new Error('resolveSelectedTextRangeForNote requires note element');
    }

    const noteContent = noteElement.querySelector('.note-content');
    if (!(noteContent instanceof HTMLElement)) {
        throw new Error('Context-menu note missing content element');
    }

    const selection = window.getSelection();
    if (!selection || selection.rangeCount === 0 || selection.isCollapsed) {
        return null;
    }
    if (selection.toString().length === 0) {
        return null;
    }
    if (!noteContent.contains(selection.anchorNode) || !noteContent.contains(selection.focusNode)) {
        return null;
    }

    return selection.getRangeAt(0).cloneRange();
}

async function copySelectedTextRange(selectedTextRange) {
    if (!(selectedTextRange instanceof Range)) {
        throw new Error('copySelectedTextRange requires Range');
    }

    const selection = window.getSelection();
    if (!selection) {
        throw new Error('Selection API unavailable');
    }
    selection.removeAllRanges();
    selection.addRange(selectedTextRange.cloneRange());

    const copied = document.execCommand('copy');
    if (copied) {
        if (ModeContext.clipboardMode !== 'system') {
            ModeContext.setClipboardMode('system');
        }
        return;
    }

    const selectedText = selectedTextRange.toString();
    const clipboard = navigator.clipboard;
    if (!clipboard || typeof clipboard.writeText !== 'function') {
        throw new Error('Unable to copy selected text: Clipboard API unavailable');
    }
    await clipboard.writeText(selectedText);
    if (ModeContext.clipboardMode !== 'system') {
        ModeContext.setClipboardMode('system');
    }
}

function markContextMenuNoteClipboard(noteId) {
    if (typeof noteId !== 'string' || noteId.length === 0) {
        throw new Error('markContextMenuNoteClipboard requires noteId');
    }
    if (ModeContext.clipboardMode !== 'note') {
        ModeContext.setClipboardMode('note');
    }
    if (ModeContext.clipboardNoteId !== noteId) {
        ModeContext.setClipboardNoteId(noteId);
    }
}

async function copyNoteFromContextMenu(noteId) {
    if (typeof noteId !== 'string' || noteId.length === 0) {
        throw new Error('copyNoteFromContextMenu requires noteId');
    }

    const copyResult = await actionCopyNoteById(noteId);
    const renderedHtml = copyResult?.html;
    const renderedPlainText = copyResult?.plain_text;
    if (renderedHtml || renderedPlainText) {
        await writeRenderedNoteToSystemClipboard({
            renderedHtml,
            renderedPlainText,
            logger: Logger,
        });
    }

    const copiedNoteId = copyResult?.note_id;
    markContextMenuNoteClipboard(
        typeof copiedNoteId === 'string' && copiedNoteId.length > 0 ? copiedNoteId : noteId,
    );
}

async function pasteReferenceFromContextMenu(noteId) {
    if (typeof noteId !== 'string' || noteId.length === 0) {
        throw new Error('pasteReferenceFromContextMenu requires noteId');
    }

    const referenceNoteId = ModeContext.clipboardNoteId;
    if (typeof referenceNoteId !== 'string' || referenceNoteId.length === 0) {
        throw new Error('Cannot paste reference: no copied note UUID available');
    }

    await focusNoteForContextAction(noteId);
    insertReferenceTokenIntoActiveEditor(`![[${referenceNoteId}]]`);
}

async function pasteReferenceAsChildFromContextMenu(noteId) {
    if (typeof noteId !== 'string' || noteId.length === 0) {
        throw new Error('pasteReferenceAsChildFromContextMenu requires noteId');
    }

    const referenceNoteId = ModeContext.clipboardNoteId;
    if (typeof referenceNoteId !== 'string' || referenceNoteId.length === 0) {
        throw new Error('Cannot paste reference as child: no copied note UUID available');
    }

    await focusNoteForContextAction(noteId);
    await createChildNote();
    insertReferenceTokenIntoActiveEditor(`![[${referenceNoteId}]]`);
}

function showNoteContextMenu(event, noteId, imageContext, selectedTextRange) {
    if (typeof noteId !== 'string' || noteId.trim() === '') {
        return;
    }
    if (!event) {
        throw new Error('showNoteContextMenu called without event');
    }
    if (typeof event.clientX !== 'number' || typeof event.clientY !== 'number') {
        throw new Error('Context menu event missing coordinates');
    }

    const hasSelectedText = selectedTextRange instanceof Range;
    const hasNoteClipboard = (
        ModeContext.clipboardMode === 'note'
        && typeof ModeContext.clipboardNoteId === 'string'
        && ModeContext.clipboardNoteId.length > 0
    );
    const context = {
        kind: 'note',
        noteId,
        imageContext,
        hasSelectedText,
        hasNoteClipboard,
    };
    const items = buildContextMenuItems(context, {
        onCopySelection: () => {
            void CommandGate.run('contextMenu.selection.copy', async () => {
                await copySelectedTextRange(selectedTextRange);
            });
        },
        onCopyNote: (targetNoteId) => {
            void CommandGate.run('contextMenu.note.copy', async () => {
                await copyNoteFromContextMenu(targetNoteId);
            });
        },
        onPasteNote: (targetNoteId) => {
            void CommandGate.run('contextMenu.note.paste', async () => {
                await focusNoteForContextAction(targetNoteId);
                await actionPasteNoteSibling();
            });
        },
        onPasteNoteChild: (targetNoteId) => {
            void CommandGate.run('contextMenu.note.paste_child', async () => {
                await focusNoteForContextAction(targetNoteId);
                await actionPasteNoteChild();
            });
        },
        onPasteReference: (targetNoteId) => {
            void CommandGate.run('contextMenu.note.paste_reference', async () => {
                await pasteReferenceFromContextMenu(targetNoteId);
            });
        },
        onPasteReferenceChild: (targetNoteId) => {
            void CommandGate.run('contextMenu.note.paste_reference_child', async () => {
                await pasteReferenceAsChildFromContextMenu(targetNoteId);
            });
        },
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

    if (isInRightRail(event)) {
        showCalendarRailContextMenu(event);
        return;
    }

    if (isInLeftTabRail(event)) {
        showTabsRailContextMenu(event);
        return;
    }

    const element = resolveEventElement(event.target);
    if (!element) {
        return;
    }

    const rhsPanel = element.closest('#rhs-panel');
    if (rhsPanel) {
        showCalendarRailContextMenu(event);
        return;
    }

    const tabsPanel = element.closest('#search-contexts-list');
    if (tabsPanel) {
        showTabsRailContextMenu(event);
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
        const selectedTextRange = resolveSelectedTextRangeForNote(noteElement);
        showNoteContextMenu(event, noteElement.dataset.noteId, imageContext, selectedTextRange);
    }
}

export function initContextMenuEvents() {
    initContextMenuService();
    document.addEventListener('contextmenu', handleContextMenu, { capture: true });
    Logger.logInit('Context menu events handler');
}
