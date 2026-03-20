import { ModeContextInstance as ModeContext } from '../mode-context.js';
import * as Logger from '../mode-logger.js';
import { createNote, deleteNote, collapseNote, expandNote, getShellRun, moveNoteUp, moveNoteDown, indentNote, outdentNote, sendShellInput, toggleTodoDone, runShellNote, toggleReferenceModeForNote } from '../actions/note-actions.js';
import { actionSelectNote, actionDeselectNote, actionSwitchNotes } from '../actions/selection-actions.js';
import { actionEnterSearchMode, actionExitSearchMode } from '../actions/search-actions.js';
import { DOMUtils } from '../../dom-utils.js'; 
import { normalizeTagBarForNewTag } from '../services/tag-bar-service.js';
import { CommandGate } from '../services/command-gate-service.js';
import { CommandPalette } from '../../command-palette/command-palette-controller.js';
import { downloadFileReference } from '../services/file-reference-service.js';
import { revealRedactedNoteWithScrollPreservation } from '../services/search-redaction-reveal-service.js';
import { navigateBackFromReferenceContext, openReferenceInCurrentTab, openReferenceInNewTab } from './keyboard-events.js';

const collapseToggleClickSkips = new WeakSet();

let selectionDragContext = null;
let ignoreClickAfterSelectionDrag = null;
let moveDragContext = null;
let ignoreClickAfterMoveDrag = null;

const MOVE_DRAG_THRESHOLD_PX = 20;
const MOVE_DRAG_THRESHOLD_SQ = MOVE_DRAG_THRESHOLD_PX * MOVE_DRAG_THRESHOLD_PX;
const CREDENTIAL_VALUE_SELECTOR = '.meta-credential-value';
const EMAIL_VALUE_SELECTOR = '.meta-email-value';
const STATUS_TOGGLE_SELECTOR = '.meta-status-toggle';
const SHELL_SELECTOR = '.meta-shell';
const SHELL_OUTPUT_SELECTOR = '.meta-shell-output';
const SHELL_INPUT_ROW_SELECTOR = '.meta-shell-output-input-row';
const SHELL_INPUT_SELECTOR = '.meta-shell-output-input';
const SHELL_SEND_SELECTOR = '.meta-shell-output-send';
const CREDENTIAL_COPY_CLASS = 'meta-credential-copied';
const COPYABLE_SELECTOR = '.meta-copyable';
const COPYABLE_COPY_CLASS = 'meta-copyable-copied';
const SHELL_RUNNING_CLASS = 'meta-shell-running';
const SHELL_RUN_TIMEOUT_SECONDS = 0;
const SHELL_POLL_INTERVAL_MS = 250;
const copyFeedbackTimers = new WeakMap();

export function initMouseEvents() {
        
    document.addEventListener('mousedown', handleCollapseToggleMouseDown, { capture: true });
    document.addEventListener('mousedown', handleMoveDragMouseDown, { capture: true });
    document.addEventListener('mousemove', handleMoveDragMouseMove, { capture: true });
    document.addEventListener('mouseup', handleMoveDragMouseUp, { capture: true });
    document.addEventListener('mousedown', handleSelectionDragMouseDown, { capture: true });
    document.addEventListener('mouseup', handleSelectionDragMouseUp, { capture: true });
    document.addEventListener('click', handleClick, { capture: true });
    document.addEventListener('mouseover', handleMouseOver, { capture: true });
    document.addEventListener('mouseout', handleMouseOut, { capture: true });

    Logger.logInit('Mouse events handler');
}

function isShellInteractiveTarget(target) {
    if (!(target instanceof Element)) {
        return false;
    }
    return Boolean(target.closest(SHELL_INPUT_ROW_SELECTOR));
}

function handleSelectionDragMouseDown(event) {
    if (!event) {
        throw new Error('handleSelectionDragMouseDown called without an event object');
    }
    if (typeof event.button !== 'number') {
        throw new Error(`Invalid MouseEvent: missing button (type: ${event.type})`);
    }
    if (event.button !== 0) {
        return;
    }
    if (!event.target) {
        throw new Error('Selection drag mousedown missing target element');
    }

    if (!ModeContext.isEditing || !ModeContext.currentNoteId) {
        selectionDragContext = null;
        return;
    }

    const noteContent = event.target.closest('.note-content');
    if (!noteContent) {
        selectionDragContext = null;
        return;
    }

    const noteElement = noteContent.closest('.note');
    if (!noteElement) {
        throw new Error('Found .note-content without parent .note element in selection drag handler');
    }

    const noteId = noteElement.dataset.noteId;
    if (!noteId) {
        throw new Error('Note element missing data-note-id attribute in selection drag handler');
    }

    if (noteId !== ModeContext.currentNoteId) {
        selectionDragContext = null;
        return;
    }

    selectionDragContext = {
        noteId,
        noteContent,
        startedAt: performance.now(),
    };
}

function setMoveDragCursorActive(isActive) {
    const body = document.body;
    if (!body) {
        throw new Error('Document body missing while toggling drag cursor');
    }
    body.classList.toggle('note-drag-active', Boolean(isActive));
}

function handleMoveDragMouseDown(event) {
    if (!event) {
        throw new Error('handleMoveDragMouseDown called without an event object');
    }
    if (typeof event.button !== 'number') {
        throw new Error(`Invalid MouseEvent: missing button (type: ${event.type})`);
    }
    if (event.button !== 0) {
        return;
    }
    if (!event.target) {
        throw new Error('Move drag mousedown missing target element');
    }
    if (event.target instanceof Element && event.target.closest(SHELL_SELECTOR)) {
        moveDragContext = null;
        return;
    }
    if (isShellInteractiveTarget(event.target)) {
        moveDragContext = null;
        return;
    }

    if (ModeContext.isLoading) {
        moveDragContext = null;
        return;
    }

    if (ModeContext.isEditing) {
        moveDragContext = null;
        return;
    }

    const noteContent = event.target.closest('.note-content');
    if (!noteContent) {
        moveDragContext = null;
        return;
    }

    const noteElement = noteContent.closest('.note');
    if (!noteElement) {
        throw new Error('Found .note-content without parent .note element in move drag handler');
    }

    if (noteElement.classList.contains('locked') || noteElement.classList.contains('search-redacted')) {
        moveDragContext = null;
        return;
    }

    const noteId = noteElement.dataset.noteId;
    if (!noteId) {
        throw new Error('Note element missing data-note-id attribute in move drag handler');
    }

    if (event.clientX === undefined || event.clientY === undefined) {
        throw new Error(`Invalid MouseEvent: missing coordinates (type: ${event.type})`);
    }

    moveDragContext = {
        noteId,
        startX: event.clientX,
        startY: event.clientY,
        dragActive: false,
    };
}

function handleMoveDragMouseMove(event) {
    const context = moveDragContext;
    if (!context) {
        return;
    }
    if (!event) {
        throw new Error('handleMoveDragMouseMove called without an event object');
    }
    if (event.clientX === undefined || event.clientY === undefined) {
        throw new Error(`Invalid MouseEvent: missing coordinates (type: ${event.type})`);
    }

    const dx = event.clientX - context.startX;
    const dy = event.clientY - context.startY;
    const distanceSq = dx * dx + dy * dy;
    const shouldBeActive = distanceSq >= MOVE_DRAG_THRESHOLD_SQ;

    if (shouldBeActive && !context.dragActive) {
        context.dragActive = true;
        setMoveDragCursorActive(true);
    }
    if (!shouldBeActive && context.dragActive) {
        context.dragActive = false;
        setMoveDragCursorActive(false);
    }

    if (context.dragActive) {
        event.preventDefault();
        const selection = window.getSelection();
        if (selection && selection.rangeCount > 0) {
            selection.removeAllRanges();
        }
    }
}

function resolveDragDirection(dx, dy) {
    const absX = Math.abs(dx);
    const absY = Math.abs(dy);
    if (absX > absY) {
        return dx > 0 ? 'right' : 'left';
    }
    return dy > 0 ? 'down' : 'up';
}

function handleMoveDragMouseUp(event) {
    const context = moveDragContext;
    moveDragContext = null;
    if (!context) {
        return;
    }
    if (!event) {
        throw new Error('handleMoveDragMouseUp called without an event object');
    }
    if (typeof event.button !== 'number') {
        throw new Error(`Invalid MouseEvent: missing button (type: ${event.type})`);
    }
    if (event.button !== 0) {
        return;
    }
    if (event.clientX === undefined || event.clientY === undefined) {
        throw new Error(`Invalid MouseEvent: missing coordinates (type: ${event.type})`);
    }

    if (context.dragActive) {
        setMoveDragCursorActive(false);
    }

    const dx = event.clientX - context.startX;
    const dy = event.clientY - context.startY;
    const distanceSq = dx * dx + dy * dy;
    if (distanceSq < MOVE_DRAG_THRESHOLD_SQ) {
        return;
    }

    if (ModeContext.isEditing) {
        return;
    }

    ignoreClickAfterMoveDrag = {
        ignoreUntil: performance.now() + 500,
    };

    event.preventDefault();
    event.stopPropagation();

    const direction = resolveDragDirection(dx, dy);

    if (!ModeContext.isConnected) {
        Logger.logNoop('Move drag ignored while disconnected from server', {
            noteId: context.noteId,
            direction,
            isConnected: false,
        });
        return;
    }

    if (!context.noteId) {
        throw new Error('Move drag context missing noteId on mouseup');
    }

    if (direction === 'up') {
        void CommandGate.run('mouse.drag_up', async () => {
            await moveNoteUp(context.noteId);
        });
        return;
    }
    if (direction === 'down') {
        void CommandGate.run('mouse.drag_down', async () => {
            await moveNoteDown(context.noteId);
        });
        return;
    }
    if (direction === 'right') {
        void CommandGate.run('mouse.drag_indent', async () => {
            await indentNote(context.noteId);
        });
        return;
    }
    if (direction === 'left') {
        void CommandGate.run('mouse.drag_outdent', async () => {
            await outdentNote(context.noteId);
        });
        return;
    }

    Logger.logNoop('Move drag resolved to unknown direction', {
        noteId: context.noteId,
        dx,
        dy,
    });
}

function handleSelectionDragMouseUp(event) {
    if (!event) {
        throw new Error('handleSelectionDragMouseUp called without an event object');
    }
    if (typeof event.button !== 'number') {
        throw new Error(`Invalid MouseEvent: missing button (type: ${event.type})`);
    }
    if (event.button !== 0) {
        return;
    }
    if (!event.target) {
        throw new Error('Selection drag mouseup missing target element');
    }

    const context = selectionDragContext;
    selectionDragContext = null;
    if (!context) {
        return;
    }

    if (!ModeContext.isEditing || ModeContext.currentNoteId !== context.noteId) {
        return;
    }

    const selection = window.getSelection();
    if (!selection || selection.rangeCount === 0 || selection.isCollapsed) {
        return;
    }

    const anchorNode = selection.anchorNode;
    const focusNode = selection.focusNode;
    if (!anchorNode || !focusNode) {
        throw new Error('Selection missing anchorNode/focusNode after selection drag');
    }

    if (!context.noteContent.contains(anchorNode) || !context.noteContent.contains(focusNode)) {
        return;
    }

    const releasedOutsideContent = !event.target.closest('.note-content');
    if (!releasedOutsideContent) {
        return;
    }

    ignoreClickAfterSelectionDrag = {
        noteId: context.noteId,
        ignoreUntil: performance.now() + 500,
    };
}

function handleCollapseToggleMouseDown(event) {
    if (!event) {
        throw new Error('handleCollapseToggleMouseDown called without an event object');
    }

    if (!event.target) {
        throw new Error('Collapse toggle mousedown missing target element');
    }

    if (typeof event.button !== 'number') {
        throw new Error(`Invalid MouseEvent: missing button (type: ${event.type})`);
    }

    if (event.button !== 0) {
        return;
    }

    const collapseToggle = event.target.closest('.note-collapse-toggle');
    if (!collapseToggle) {
        return;
    }

    if (ModeContext.isLoading) {
        Logger.logNoop('Collapse toggle mousedown ignored while system is loading', {
            eventType: event.type,
            isLoading: true
        });
        return;
    }

    if (!ModeContext.isConnected) {
        Logger.logNoop('Collapse toggle mousedown ignored while disconnected from server', {
            eventType: event.type,
            targetElement: collapseToggle.tagName,
            isConnected: false
        });
        event.preventDefault();
        event.stopPropagation();
        return;
    }

    collapseToggleClickSkips.add(collapseToggle);
    handleCollapseToggleInteraction(event, collapseToggle, 'mousedown');
}

function handleClick(event) {
    if (!event) {
        throw new Error('handleClick called without an event object');
    }
        
    if (event.clientX === undefined || event.clientY === undefined) {
        throw new Error(`Invalid MouseEvent: missing coordinates (type: ${event.type})`);
    }
        
    if (!event.target) {
        throw new Error('Click event missing target element');
    }

    if (event.target instanceof Element && event.target.closest('.modal')) {
        return;
    }

    const contextMenu = event.target.closest('#context-menu');
    if (contextMenu) {
        return;
    }
    if (isShellInteractiveTarget(event.target)) {
        return;
    }

    if (ModeContext.isLoading) {
        Logger.logNoop('Click event ignored while system is loading', {
            eventType: event.type,
            targetElement: event.target.tagName,
            isLoading: true
        });
        return; 
    }

    if (ignoreClickAfterMoveDrag && performance.now() > ignoreClickAfterMoveDrag.ignoreUntil) {
        ignoreClickAfterMoveDrag = null;
    }
    if (ignoreClickAfterMoveDrag) {
        ignoreClickAfterMoveDrag = null;
        event.preventDefault();
        event.stopPropagation();
        return;
    }

    if (
        ignoreClickAfterSelectionDrag &&
        ignoreClickAfterSelectionDrag.noteId === ModeContext.currentNoteId &&
        performance.now() <= ignoreClickAfterSelectionDrag.ignoreUntil
    ) {
        ignoreClickAfterSelectionDrag = null;
        event.preventDefault();
        event.stopPropagation();
        return;
    }

    if (handleReferenceToggleClick(event)) {
        return;
    }

    if (handleReferenceBackButtonClick(event)) {
        return;
    }

    if (handleFileReferenceClick(event)) {
        return;
    }

    if (handleReferenceLinkClick(event)) {
        return;
    }

    if (handleBacklinkItemClick(event)) {
        return;
    }

    if (event.target.closest('#backlinks-panel')) {
        return;
    }

    if (handleTodoToggleClick(event)) {
        return;
    }

    if (handleCredentialCopyClick(event)) {
        return;
    }

    if (handleEmailClick(event)) {
        return;
    }

    if (handleCopyableClick(event)) {
        return;
    }

    if (handleShellRunClick(event)) {
        return;
    }

    const menuButton = event.target.closest('#menu-button');
    if (menuButton) {
        event.preventDefault();
        event.stopPropagation();
        void CommandPalette.toggle();
        return;
    }

    ignoreClickAfterSelectionDrag = null;

    const toolbarElement = event.target.closest('#rich-text-toolbar');
    if (toolbarElement) {
        Logger.logDebug('Click inside rich text toolbar', {
            eventType: event.type
        }, Logger.LogCategory.EVENT);
        return;
    }

    const fileReferenceInputElement = event.target.closest('#file-reference-input');
    if (fileReferenceInputElement) {
        Logger.logDebug('Click on hidden file reference input ignored', {
            eventType: event.type,
        }, Logger.LogCategory.EVENT);
        return;
    }

    const tagBarElement = event.target.closest('.note-tag-bar');
    if (tagBarElement) {
        const tagBarInput = event.target.closest('.note-tag-bar-input');
        if (tagBarInput && event.detail === 1) {
            const noteElement = tagBarInput.closest('.note');
            const noteId = noteElement?.dataset?.noteId;
            if (noteElement && noteId && ModeContext.isEditing && ModeContext.currentNoteId === noteId) {
                window.setTimeout(() => {
                    if (!ModeContext.isEditing || ModeContext.currentNoteId !== noteId) {
                        return;
                    }
                    if (document.activeElement !== tagBarInput) {
                        return;
                    }

                    const value = typeof tagBarInput.value === 'string' ? tagBarInput.value : '';
                    const end = value.length;
                    const selectionStart = tagBarInput.selectionStart;
                    const selectionEnd = tagBarInput.selectionEnd;
                    if (selectionStart !== end || selectionEnd !== end) {
                        return;
                    }

                    normalizeTagBarForNewTag(noteElement, tagBarInput);
                }, 0);
            }
        }

        Logger.logDebug('Click inside tag bar', {
            eventType: event.type
        }, Logger.LogCategory.EVENT);
        return;
    }

    const tabContextsElement = event.target.closest('#search-contexts-list');
    if (tabContextsElement) {
        return;
    }
    
    // Check if we're disconnected from server
    if (!ModeContext.isConnected) {
        const noteContent = event.target.closest('.note-content');
        const searchField = event.target.closest('#search-input');
        const createButton = event.target.closest('.add-note');
        const collapseToggle = event.target.closest('.note-collapse-toggle');
        
        // Only allow certain actions when disconnected
        if (noteContent || createButton || collapseToggle) {
            Logger.logNoop('Click event ignored while disconnected from server', {
                eventType: event.type,
                targetElement: event.target.tagName,
                isConnected: false
            });
            event.preventDefault();
            event.stopPropagation();
            return;
        }
        // Allow clicking on search field even when disconnected
    }

    const coordinates = {
        x: event.clientX,
        y: event.clientY
    };

    const collapseToggle = event.target.closest('.note-collapse-toggle');
    if (collapseToggle) {
        if (collapseToggleClickSkips.has(collapseToggle)) {
            event.preventDefault();
            event.stopPropagation();
            collapseToggleClickSkips.delete(collapseToggle);
            return;
        }

        handleCollapseToggleInteraction(event, collapseToggle, 'click');
        return;
    }

    const noteContent = event.target.closest('.note-content');
    const searchField = event.target.closest('#search-input');
    const createButton = event.target.closest('.add-note');
    const deleteButton = event.target.closest('#trash-can');

    if (deleteButton) {
                
        if (ModeContext.isSearching) {
            actionExitSearchMode();
        }

        const noteId = ModeContext.currentNoteId;
                
        if (noteId) {
            Logger.logDebug('Delete button clicked for current note', { 
                noteId,
                coordinates 
            }, Logger.LogCategory.EVENT);

            void CommandGate.run('mouse.delete', async () => {
                await deleteNote(noteId);
            });
        } else {
                        
            Logger.logNoop('Delete button clicked but no note is selected', { 
                coordinates 
            });
        }
    } else if (noteContent) {
        const noteElement = noteContent.closest('.note');
        if (!noteElement) {
            throw new Error('Found .note-content without parent .note element');
        }
        
        // Check if note is locked - don't allow interaction
        if (noteElement.classList.contains('locked')) {
            Logger.logNoop('Click on locked note ignored', {
                noteId: noteElement.dataset.noteId,
                reason: 'note_locked'
            });
            event.preventDefault();
            event.stopPropagation();
            return;
        }

        const noteId = noteElement.dataset.noteId;
        if (!noteId) {
            throw new Error('Note element missing data-note-id attribute');
        }

        if (noteElement.classList.contains('search-redacted')) {
            const revealResult = revealRedactedNoteWithScrollPreservation(noteId);
            Logger.logAction('reveal search-redacted note', {
                noteId,
                result: revealResult.reason,
            });
            event.preventDefault();
            event.stopPropagation();
            return;
        }
                
        const rect = noteContent.getBoundingClientRect();
        if (!rect || typeof rect.left !== 'number' || typeof rect.right !== 'number' || 
                typeof rect.top !== 'number' || typeof rect.bottom !== 'number') {
            throw new Error(`Invalid bounding rect for note content: ${JSON.stringify(rect)}`);
        }
                
        const isWithinBounds = (
            coordinates.x >= rect.left &&
            coordinates.x <= rect.right &&
            coordinates.y >= rect.top &&
            coordinates.y <= rect.bottom
        );
                
        if (isWithinBounds) {
                        
            if (ModeContext.isSearching) {
                console.log('DEBUG: About to call exitSearchMode', { 
                    isSearching: ModeContext.isSearching, 
                    where: 'click in note' 
                });
                actionExitSearchMode();
            } else {
                console.log('DEBUG: Search mode already inactive', { 
                    isSearching: ModeContext.isSearching, 
                    where: 'click in note' 
                });
            }

            if (!ModeContext.isEditing || ModeContext.currentNoteId !== noteId) {
                // Don't calculate or save cursor position when entering edit mode
                // The click position on rendered content (e.g., LaTeX) doesn't map meaningfully 
                // to cursor position in source text

				if (ModeContext.currentNoteId) {
					void CommandGate.run('mouse.switch_note', async () => {
						await actionSwitchNotes(noteId, { initialCaretVisibility: 'hidden' });
					});
				} else {
					void CommandGate.run('mouse.select_note', async () => {
						await actionSelectNote(noteId, { initialCaretVisibility: 'hidden' });
					});
				}
                                
                Logger.logDebug('Click in note content - selecting note', { 
                    noteId,
                    coordinates,
                    isEditing: true
                }, Logger.LogCategory.EVENT);
            } else {
                if (ModeContext.isCaretHidden && ModeContext.currentNoteId === noteId) {
                    DOMUtils.revealCaret(noteElement);
                    ModeContext.markCaretVisible();
                }

                Logger.logNoop('Click in already selected note - no action needed', { 
                    noteId,
                    coordinates,
                    isEditing: true
                });
            }
		} else {
			            
			if (ModeContext.isEditing) {
				void CommandGate.run('mouse.deselect', async () => {
					await actionDeselectNote();
				});
			}
                        
            Logger.logDebug('Click near note but outside content bounds', {
                noteId,
                coordinates,
                elementBounds: {
                    left: rect.left,
                    right: rect.right,
                    top: rect.top,
                    bottom: rect.bottom
                },
                isEditing: false
            }, Logger.LogCategory.EVENT);
        }
	} else if (searchField) {
		void CommandGate.run('mouse.enter_search_mode', async () => {
			await actionEnterSearchMode();
		});
	                
		Logger.logDebug('Click in search field', { coordinates }, Logger.LogCategory.EVENT);
	} else if (createButton) {
        
        if (ModeContext.isLoading) {
            Logger.logNoop('Create button clicked while system is loading - ignoring', {
                coordinates,
                isLoading: true
            });
            return; 
        }
                
        if (ModeContext.isSearching) {
            console.log('DEBUG: About to call exitSearchMode', { 
                isSearching: ModeContext.isSearching, 
                where: 'create note button' 
            });
            actionExitSearchMode();
        } else {
            console.log('DEBUG: Search mode already inactive', { 
                isSearching: ModeContext.isSearching, 
                where: 'create note button' 
            });
        }
                
        Logger.logDebug('Create note button clicked', { coordinates }, Logger.LogCategory.EVENT);
		void CommandGate.run('mouse.create_note', async () => {
			await createNote();
		});
	} else {

		if (ModeContext.isEditing) {
			void CommandGate.run('mouse.deselect', async () => {
				await actionDeselectNote();
			});
			            
			Logger.logDebug('Click outside any note - exiting edit mode', {
				coordinates,
                isEditing: false,
                currentNoteId: null
            }, Logger.LogCategory.EVENT);
        }

        if (ModeContext.isSearching) {
            console.log('DEBUG: About to call exitSearchMode', { 
                isSearching: ModeContext.isSearching, 
                where: 'click outside handler' 
            });
            actionExitSearchMode();
        } else {
            console.log('DEBUG: Search mode already inactive', { 
                isSearching: ModeContext.isSearching, 
                where: 'click outside handler' 
            });
        }
    }
}

function parseReferenceOccurrenceIndex(rawValue) {
    const parsed = Number.parseInt(rawValue, 10);
    if (!Number.isInteger(parsed) || parsed < 0) {
        throw new Error(`Invalid reference occurrence index: ${rawValue}`);
    }
    return parsed;
}

function getReferenceContainerFromEvent(event, selector) {
    if (!event.target) {
        throw new Error('Reference interaction missing target element');
    }
    const interactiveElement = event.target.closest(selector);
    if (!interactiveElement) {
        return null;
    }
    const container = interactiveElement.closest('.note-reference-block');
    if (!container) {
        throw new Error('Reference interaction missing .note-reference-block container');
    }
    return container;
}

function handleReferenceToggleClick(event) {
    const container = getReferenceContainerFromEvent(event, '.note-reference-toggle');
    if (!container) {
        return false;
    }

    event.preventDefault();
    event.stopPropagation();

    if (ModeContext.isEditing) {
        return true;
    }
    if (!ModeContext.isConnected) {
        Logger.logNoop('Reference toggle click ignored while disconnected', {
            isConnected: false,
        });
        return true;
    }

    const hostNoteId = container.dataset.refHostNoteId;
    const referenceNoteId = container.dataset.refNoteId;
    const mode = container.dataset.refTargetMode;
    const occurrenceRaw = container.dataset.refOccurrence;
    if (typeof hostNoteId !== 'string' || hostNoteId.length === 0) {
        throw new Error('Reference toggle missing host note id');
    }
    if (typeof referenceNoteId !== 'string' || referenceNoteId.length === 0) {
        throw new Error('Reference toggle missing reference note id');
    }
    if (mode !== 'embed' && mode !== 'link') {
        throw new Error(`Reference toggle has invalid target mode: ${mode}`);
    }
    const occurrenceIndex = parseReferenceOccurrenceIndex(occurrenceRaw);

    void CommandGate.run('mouse.toggle_reference_mode', async () => {
        await toggleReferenceModeForNote(hostNoteId, referenceNoteId, occurrenceIndex, mode);
    });
    return true;
}

function handleReferenceLinkClick(event) {
    const container = getReferenceContainerFromEvent(event, '.note-reference-link');
    if (!container) {
        return false;
    }

    event.preventDefault();
    event.stopPropagation();

    if (ModeContext.isEditing) {
        return true;
    }
    if (!ModeContext.isConnected) {
        Logger.logNoop('Reference link click ignored while disconnected', {
            isConnected: false,
        });
        return true;
    }

    const referenceNoteId = container.dataset.refNoteId;
    if (typeof referenceNoteId !== 'string' || referenceNoteId.length === 0) {
        throw new Error('Reference link missing target note id');
    }

    void CommandGate.run('mouse.open_reference_in_new_tab', async () => {
        await openReferenceInNewTab(referenceNoteId);
    });
    return true;
}

function handleFileReferenceClick(event) {
    if (!event.target) {
        throw new Error('File reference click missing target element');
    }

    const button = event.target.closest('.note-file-reference-link, .note-file-image-download-link');
    if (!button) {
        return false;
    }

    event.preventDefault();
    event.stopPropagation();

    if (ModeContext.isEditing) {
        return true;
    }
    if (!ModeContext.isConnected) {
        Logger.logNoop('File reference click ignored while disconnected', {
            isConnected: false,
        });
        return true;
    }

    const fileId = button.dataset.fileRefId;
    if (typeof fileId !== 'string' || fileId.length === 0) {
        throw new Error('File reference click missing file id');
    }

    void CommandGate.run('mouse.download_file_reference', async () => {
        await downloadFileReference(fileId);
    });
    return true;
}

function handleReferenceBackButtonClick(event) {
    if (!event.target) {
        throw new Error('Reference back click missing target element');
    }

    const backButton = event.target.closest('#reference-back-button');
    if (!backButton) {
        return false;
    }

    event.preventDefault();
    event.stopPropagation();

    if (!ModeContext.isConnected) {
        Logger.logNoop('Reference back click ignored while disconnected', {
            isConnected: false,
        });
        return true;
    }

    if (backButton instanceof HTMLButtonElement && backButton.disabled) {
        return true;
    }

    void CommandGate.run('mouse.reference_back', async () => {
        await navigateBackFromReferenceContext();
    });
    return true;
}

function handleBacklinkItemClick(event) {
    if (!event.target) {
        throw new Error('Backlink click missing target element');
    }

    const backlinkItem = event.target.closest('.backlink-item');
    if (!backlinkItem) {
        return false;
    }

    event.preventDefault();
    event.stopPropagation();

    if (!ModeContext.isConnected) {
        Logger.logNoop('Backlink click ignored while disconnected', {
            isConnected: false,
        });
        return true;
    }

    const noteId = backlinkItem.dataset.backlinkNoteId;
    if (typeof noteId !== 'string' || noteId.length === 0) {
        throw new Error('Backlink click missing data-backlink-note-id');
    }

    void CommandGate.run('mouse.open_backlink_in_new_tab', async () => {
        await openReferenceInCurrentTab(noteId);
    });
    return true;
}

function handleTodoToggleClick(event) {
    if (!event) {
        throw new Error('handleTodoToggleClick called without an event object');
    }
    if (!event.target) {
        throw new Error('Todo toggle click missing target element');
    }

    const toggleElement = event.target.closest(STATUS_TOGGLE_SELECTOR);
    if (!toggleElement) {
        return false;
    }

    if (ModeContext.isEditing) {
        return false;
    }

    if (!ModeContext.isConnected) {
        return false;
    }

    const noteElement = toggleElement.closest('.note');
    if (!noteElement) {
        throw new Error('Todo toggle missing parent note element');
    }
    if (noteElement.classList.contains('locked') || noteElement.classList.contains('search-redacted')) {
        return false;
    }

    const noteId = noteElement.dataset.noteId;
    if (!noteId) {
        throw new Error('Todo toggle note missing data-note-id attribute');
    }

    event.preventDefault();
    event.stopPropagation();

    void CommandGate.run('mouse.toggle_todo', async () => {
        await toggleTodoDone(noteId);
    });

    return true;
}

function handleCredentialCopyClick(event) {
    if (!event) {
        throw new Error('handleCredentialCopyClick called without an event object');
    }
    if (!event.target) {
        throw new Error('Credential copy click missing target element');
    }

    const valueElement = event.target.closest(CREDENTIAL_VALUE_SELECTOR);
    if (!valueElement) {
        return false;
    }

    const copyValue = valueElement.dataset.copyValue;
    if (typeof copyValue !== 'string') {
        throw new Error('Credential value missing data-copy-value attribute');
    }

    event.preventDefault();
    event.stopPropagation();

    triggerCopyFeedback(valueElement, CREDENTIAL_COPY_CLASS);
    void copyTextToClipboard(copyValue, valueElement, CREDENTIAL_COPY_CLASS);
    Logger.logAction('credential.copy', { valueLength: copyValue.length });
    return true;
}

function handleEmailClick(event) {
    if (!event) {
        throw new Error('handleEmailClick called without an event object');
    }
    if (!event.target) {
        throw new Error('Email click missing target element');
    }

    const emailElement = event.target.closest(EMAIL_VALUE_SELECTOR);
    if (!emailElement) {
        return false;
    }

    if (ModeContext.isEditing) {
        return false;
    }

    event.stopPropagation();
    return true;
}

function handleCopyableClick(event) {
    if (!event) {
        throw new Error('handleCopyableClick called without an event object');
    }
    if (!event.target) {
        throw new Error('Copyable click missing target element');
    }

    const copyableElement = event.target.closest(COPYABLE_SELECTOR);
    if (!copyableElement) {
        return false;
    }

    if (ModeContext.isEditing) {
        return false;
    }

    const selection = window.getSelection();
    if (selection && !selection.isCollapsed) {
        return false;
    }

    if (event.target.closest('a')) {
        return false;
    }

    let copyValue = '';
    if (typeof copyableElement.dataset.copyValue === 'string') {
        copyValue = copyableElement.dataset.copyValue;
    } else if (copyableElement.textContent !== null) {
        copyValue = copyableElement.textContent;
    }

    copyValue = normalizeCopyableText(copyValue);
    if (copyValue === '') {
        return false;
    }

    event.preventDefault();
    event.stopPropagation();

    void copyTextToClipboard(copyValue, copyableElement, COPYABLE_COPY_CLASS);
    Logger.logAction('copyable.copy', { valueLength: copyValue.length });
    return true;
}

function normalizeCopyableText(text) {
    if (typeof text !== 'string') {
        return '';
    }
    const normalized = text.replace(/\u00a0/g, ' ');
    if (!normalized.includes('\n')) {
        return normalized.trimStart();
    }
    const lines = normalized.split('\n');
    const nonEmpty = lines.filter((line) => line.trim() !== '');
    if (nonEmpty.length === 0) {
        return normalized;
    }
    const indents = nonEmpty.map((line) => line.match(/^[ \\t]*/)[0].length);
    const minIndent = Math.min(...indents);
    if (minIndent <= 0) {
        return normalized;
    }
    return lines
        .map((line) => (line.startsWith(' '.repeat(minIndent)) ? line.slice(minIndent) : line))
        .join('\n');
}

function ensureShellOutputElement(shellElement) {
    if (!shellElement) {
        throw new Error('ensureShellOutputElement requires shellElement');
    }
    let outputElement = shellElement.querySelector(SHELL_OUTPUT_SELECTOR);
    if (outputElement) {
        return outputElement;
    }
    outputElement = document.createElement('div');
    outputElement.className = 'meta-shell-output';
    outputElement.setAttribute('aria-live', 'polite');
    shellElement.appendChild(outputElement);
    return outputElement;
}

function ensureShellOutputStructure(outputElement, noteId) {
    if (!outputElement) {
        throw new Error('ensureShellOutputStructure requires outputElement');
    }
    if (typeof noteId !== 'string' || noteId === '') {
        throw new Error('ensureShellOutputStructure requires noteId');
    }
    outputElement.dataset.noteId = noteId;

    let header = outputElement.querySelector('.meta-shell-output-header');
    if (!(header instanceof HTMLElement)) {
        header = document.createElement('div');
        header.className = 'meta-shell-output-header';
        outputElement.appendChild(header);
    }

    let statusBadge = outputElement.querySelector('.meta-shell-output-status');
    if (!(statusBadge instanceof HTMLElement)) {
        statusBadge = document.createElement('span');
        statusBadge.className = 'meta-shell-output-status';
        header.appendChild(statusBadge);
    }

    let duration = outputElement.querySelector('.meta-shell-output-duration');
    if (!(duration instanceof HTMLElement)) {
        duration = document.createElement('span');
        duration.className = 'meta-shell-output-duration';
        header.appendChild(duration);
    }

    let errorRow = outputElement.querySelector('.meta-shell-output-message-error');
    if (!(errorRow instanceof HTMLElement)) {
        errorRow = document.createElement('div');
        errorRow.className = 'meta-shell-output-message meta-shell-output-message-error';
        outputElement.appendChild(errorRow);
    }

    let stdoutBlock = outputElement.querySelector('.meta-shell-output-stdout');
    if (!(stdoutBlock instanceof HTMLElement)) {
        stdoutBlock = document.createElement('pre');
        stdoutBlock.className = 'meta-shell-output-stdout';
        outputElement.appendChild(stdoutBlock);
    }

    let stderrBlock = outputElement.querySelector('.meta-shell-output-stderr');
    if (!(stderrBlock instanceof HTMLElement)) {
        stderrBlock = document.createElement('pre');
        stderrBlock.className = 'meta-shell-output-stderr';
        outputElement.appendChild(stderrBlock);
    }

    let emptyRow = outputElement.querySelector('.meta-shell-output-empty');
    if (!(emptyRow instanceof HTMLElement)) {
        emptyRow = document.createElement('div');
        emptyRow.className = 'meta-shell-output-empty';
        outputElement.appendChild(emptyRow);
    }

    let inputRow = outputElement.querySelector(SHELL_INPUT_ROW_SELECTOR);
    if (!(inputRow instanceof HTMLElement)) {
        inputRow = document.createElement('div');
        inputRow.className = 'meta-shell-output-input-row';

        const inputElement = document.createElement('input');
        inputElement.className = 'meta-shell-output-input';
        inputElement.type = 'text';
        inputElement.placeholder = 'Send input to running shell';
        inputElement.autocomplete = 'off';
        inputElement.spellcheck = false;
        inputElement.addEventListener('keydown', (event) => {
            if (event.key !== 'Enter') {
                return;
            }
            event.preventDefault();
            event.stopPropagation();
            submitShellInput(outputElement).catch((error) => {
                const shellElement = outputElement.closest(SHELL_SELECTOR);
                if (!(shellElement instanceof HTMLElement)) {
                    throw error;
                }
                renderShellError(outputElement, shellElement, error);
            });
        });

        const sendButton = document.createElement('button');
        sendButton.className = 'meta-shell-output-send';
        sendButton.type = 'button';
        sendButton.textContent = 'Send';
        sendButton.addEventListener('click', (event) => {
            event.preventDefault();
            event.stopPropagation();
            submitShellInput(outputElement).catch((error) => {
                const shellElement = outputElement.closest(SHELL_SELECTOR);
                if (!(shellElement instanceof HTMLElement)) {
                    throw error;
                }
                renderShellError(outputElement, shellElement, error);
            });
        });

        inputRow.appendChild(inputElement);
        inputRow.appendChild(sendButton);
        outputElement.appendChild(inputRow);
    }
}

function formatShellDuration(durationMs) {
    if (!Number.isInteger(durationMs) || durationMs < 0) {
        throw new Error('formatShellDuration requires non-negative integer durationMs');
    }
    if (durationMs === 0) {
        return '0s';
    }
    const durationSeconds = durationMs / 1000;
    if (durationSeconds < 10) {
        return `${durationSeconds.toFixed(1)}s`;
    }
    return `${Math.round(durationSeconds)}s`;
}

function renderShellSnapshot(outputElement, shellElement, result) {
    if (!outputElement) {
        throw new Error('renderShellSnapshot requires outputElement');
    }
    if (!shellElement) {
        throw new Error('renderShellSnapshot requires shellElement');
    }
    if (!result || typeof result !== 'object') {
        throw new Error('renderShellSnapshot requires result object');
    }

    const runId = result.runId;
    const status = result.status;
    const exitCode = result.exitCode;
    const stdoutText = result.stdout;
    const stderrText = result.stderr;
    const durationMs = result.durationMs;
    const errorMessage = result.errorMessage;
    const acceptsInput = result.acceptsInput;

    if (typeof runId !== 'string') {
        throw new Error('Shell result runId must be a string');
    }
    if (typeof status !== 'string') {
        throw new Error('Shell result status must be a string');
    }
    if (!Number.isInteger(exitCode)) {
        throw new Error('Shell result exitCode must be an integer');
    }
    if (typeof stdoutText !== 'string') {
        throw new Error('Shell result stdout must be a string');
    }
    if (typeof stderrText !== 'string') {
        throw new Error('Shell result stderr must be a string');
    }
    if (!Number.isInteger(durationMs) || durationMs < 0) {
        throw new Error('Shell result durationMs must be a non-negative integer');
    }
    if (typeof errorMessage !== 'string') {
        throw new Error('Shell result errorMessage must be a string');
    }
    if (typeof acceptsInput !== 'boolean') {
        throw new Error('Shell result acceptsInput must be a boolean');
    }

    const noteId = outputElement.dataset.noteId;
    if (typeof noteId !== 'string' || noteId === '') {
        throw new Error('Shell output element missing noteId');
    }

    ensureShellOutputStructure(outputElement, noteId);

    outputElement.dataset.runId = runId;
    outputElement.dataset.status = status;

    const header = outputElement.querySelector('.meta-shell-output-header');
    const statusBadge = outputElement.querySelector('.meta-shell-output-status');
    const duration = outputElement.querySelector('.meta-shell-output-duration');
    const errorRow = outputElement.querySelector('.meta-shell-output-message-error');
    const stdoutBlock = outputElement.querySelector('.meta-shell-output-stdout');
    const stderrBlock = outputElement.querySelector('.meta-shell-output-stderr');
    const emptyRow = outputElement.querySelector('.meta-shell-output-empty');
    const inputRow = outputElement.querySelector(SHELL_INPUT_ROW_SELECTOR);
    const inputElement = outputElement.querySelector(SHELL_INPUT_SELECTOR);
    const sendButton = outputElement.querySelector(SHELL_SEND_SELECTOR);

    if (!(header instanceof HTMLElement)) {
        throw new Error('Shell output header missing');
    }
    if (!(statusBadge instanceof HTMLElement)) {
        throw new Error('Shell output status badge missing');
    }
    if (!(duration instanceof HTMLElement)) {
        throw new Error('Shell output duration missing');
    }
    if (!(errorRow instanceof HTMLElement)) {
        throw new Error('Shell output error row missing');
    }
    if (!(stdoutBlock instanceof HTMLElement)) {
        throw new Error('Shell output stdout block missing');
    }
    if (!(stderrBlock instanceof HTMLElement)) {
        throw new Error('Shell output stderr block missing');
    }
    if (!(emptyRow instanceof HTMLElement)) {
        throw new Error('Shell output empty row missing');
    }
    if (!(inputRow instanceof HTMLElement)) {
        throw new Error('Shell output input row missing');
    }
    if (!(inputElement instanceof HTMLInputElement)) {
        throw new Error('Shell output input element missing');
    }
    if (!(sendButton instanceof HTMLButtonElement)) {
        throw new Error('Shell output send button missing');
    }

    statusBadge.className = 'meta-shell-output-status';
    if (status === 'running') {
        statusBadge.textContent = 'Running';
    } else if (status === 'success') {
        statusBadge.classList.add('meta-shell-output-status-ok');
        statusBadge.textContent = `Exit ${exitCode}`;
    } else if (status === 'timeout') {
        statusBadge.classList.add('meta-shell-output-status-timeout');
        statusBadge.textContent = 'Timed out';
    } else {
        statusBadge.classList.add('meta-shell-output-status-error');
        statusBadge.textContent = `Exit ${exitCode}`;
    }
    duration.textContent = formatShellDuration(durationMs);

    if (errorMessage === '') {
        errorRow.style.display = 'none';
        errorRow.textContent = '';
    } else {
        errorRow.style.display = '';
        errorRow.textContent = errorMessage;
    }

    if (stdoutText === '') {
        stdoutBlock.style.display = 'none';
        stdoutBlock.textContent = '';
    } else {
        stdoutBlock.style.display = '';
        stdoutBlock.textContent = stdoutText;
    }

    if (stderrText === '') {
        stderrBlock.style.display = 'none';
        stderrBlock.textContent = '';
    } else {
        stderrBlock.style.display = '';
        stderrBlock.textContent = stderrText;
    }

    if (stdoutText === '' && stderrText === '' && errorMessage === '') {
        emptyRow.style.display = '';
        emptyRow.textContent = status === 'running' ? 'Waiting for output...' : 'No output';
    } else {
        emptyRow.style.display = 'none';
        emptyRow.textContent = '';
    }

    inputRow.style.display = acceptsInput ? '' : 'none';
    inputElement.disabled = !acceptsInput;
    sendButton.disabled = !acceptsInput;

    if (status === 'running') {
        shellElement.classList.add(SHELL_RUNNING_CLASS);
    } else {
        shellElement.classList.remove(SHELL_RUNNING_CLASS);
    }
}

function renderShellError(outputElement, shellElement, error) {
    if (!outputElement) {
        throw new Error('renderShellError requires outputElement');
    }
    if (!shellElement) {
        throw new Error('renderShellError requires shellElement');
    }
    const noteId = outputElement.dataset.noteId;
    if (typeof noteId !== 'string' || noteId === '') {
        throw new Error('Shell output element missing noteId');
    }

    let message = 'Shell run failed';
    if (error && typeof error.message === 'string') {
        message = error.message;
    }
    renderShellSnapshot(outputElement, shellElement, {
        runId: outputElement.dataset.runId || '',
        status: 'error',
        exitCode: -1,
        stdout: '',
        stderr: '',
        durationMs: 0,
        errorMessage: message,
        acceptsInput: false,
    });
}

function delayShellPoll() {
    return new Promise((resolve) => {
        window.setTimeout(resolve, SHELL_POLL_INTERVAL_MS);
    });
}

async function submitShellInput(outputElement) {
    if (!(outputElement instanceof HTMLElement)) {
        throw new Error('submitShellInput requires outputElement');
    }
    const noteId = outputElement.dataset.noteId;
    const runId = outputElement.dataset.runId;
    const status = outputElement.dataset.status;
    const inputElement = outputElement.querySelector(SHELL_INPUT_SELECTOR);
    const sendButton = outputElement.querySelector(SHELL_SEND_SELECTOR);

    if (!(inputElement instanceof HTMLInputElement)) {
        throw new Error('Shell output input element missing');
    }
    if (!(sendButton instanceof HTMLButtonElement)) {
        throw new Error('Shell output send button missing');
    }
    if (typeof noteId !== 'string' || noteId === '') {
        throw new Error('Shell output missing noteId');
    }
    if (typeof runId !== 'string' || runId === '') {
        throw new Error('Shell output missing runId');
    }
    if (status !== 'running') {
        return;
    }

    const text = inputElement.value;
    if (text === '') {
        return;
    }

    inputElement.disabled = true;
    sendButton.disabled = true;
    try {
        const snapshot = await sendShellInput(noteId, runId, text, true);
        inputElement.value = '';
        const shellElement = outputElement.closest(SHELL_SELECTOR);
        if (!(shellElement instanceof HTMLElement)) {
            throw new Error('Shell output missing parent shell element');
        }
        renderShellSnapshot(outputElement, shellElement, snapshot);
        inputElement.focus();
    } finally {
        if (outputElement.dataset.status === 'running') {
            inputElement.disabled = false;
            sendButton.disabled = false;
        }
    }
}

async function runShellSession(shellElement, outputElement, noteId) {
    if (!(shellElement instanceof HTMLElement)) {
        throw new Error('runShellSession requires shellElement');
    }
    if (!(outputElement instanceof HTMLElement)) {
        throw new Error('runShellSession requires outputElement');
    }
    if (typeof noteId !== 'string' || noteId === '') {
        throw new Error('runShellSession requires noteId');
    }

    let snapshot = await runShellNote(noteId, SHELL_RUN_TIMEOUT_SECONDS);
    renderShellSnapshot(outputElement, shellElement, snapshot);
    const runId = snapshot.runId;
    if (typeof runId !== 'string' || runId === '') {
        return;
    }

    while (snapshot.status === 'running') {
        await delayShellPoll();
        snapshot = await getShellRun(noteId, runId);
        renderShellSnapshot(outputElement, shellElement, snapshot);
    }
}

function handleShellRunClick(event) {
    if (!event) {
        throw new Error('handleShellRunClick called without an event object');
    }
    if (!event.target) {
        throw new Error('Shell run click missing target element');
    }
    const scriptElement = event.target.closest('.meta-shell-script');
    if (!scriptElement) {
        return false;
    }
    const shellElement = scriptElement.closest(SHELL_SELECTOR);
    if (!shellElement) {
        return false;
    }

    if (ModeContext.isEditing) {
        return false;
    }

    if (!ModeContext.isConnected) {
        return false;
    }

    if (shellElement.classList.contains(SHELL_RUNNING_CLASS)) {
        return true;
    }

    const noteElement = shellElement.closest('.note');
    if (!noteElement) {
        throw new Error('Shell click missing parent note element');
    }
    if (noteElement.classList.contains('locked') || noteElement.classList.contains('search-redacted')) {
        return false;
    }
    const noteId = noteElement.dataset.noteId;
    if (!noteId) {
        throw new Error('Shell click note missing data-note-id attribute');
    }

    event.preventDefault();
    event.stopPropagation();

    const outputElement = ensureShellOutputElement(shellElement);
    ensureShellOutputStructure(outputElement, noteId);
    renderShellSnapshot(outputElement, shellElement, {
        runId: '',
        status: 'running',
        exitCode: -1,
        stdout: '',
        stderr: '',
        durationMs: 0,
        errorMessage: '',
        acceptsInput: false,
    });

    void runShellSession(shellElement, outputElement, noteId).catch((error) => {
        renderShellError(outputElement, shellElement, error);
        shellElement.classList.remove(SHELL_RUNNING_CLASS);
    });

    return true;
}

async function copyTextToClipboard(text, valueElement, feedbackClass) {
    if (typeof text !== 'string') {
        throw new Error('copyTextToClipboard requires a string');
    }
    if (typeof feedbackClass !== 'string' || feedbackClass === '') {
        throw new Error('copyTextToClipboard requires feedbackClass string');
    }

    const clipboard = navigator.clipboard;
    if (clipboard && typeof clipboard.writeText === 'function') {
        const writePromise = clipboard.writeText(text);
        if (writePromise && typeof writePromise.then === 'function') {
            const writeSucceeded = await writePromise
                .then(() => true)
                .catch((error) => {
                    let errorMessage = String(error);
                    if (error && typeof error.message === 'string') {
                        errorMessage = error.message;
                    }
                    Logger.logDebug('Clipboard writeText failed', {
                        error: errorMessage
                    }, Logger.LogCategory.EVENT);
                    return false;
                });

            if (writeSucceeded) {
                triggerCopyFeedback(valueElement, feedbackClass);
                return;
            }
        }
    }

    const body = document.body;
    if (!body) {
        throw new Error('Document body missing during clipboard fallback');
    }

    const textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.setAttribute('readonly', '');
    textarea.style.position = 'fixed';
    textarea.style.opacity = '0';
    textarea.style.pointerEvents = 'none';
    textarea.style.left = '-9999px';
    textarea.style.top = '0';

    body.appendChild(textarea);
    textarea.focus();
    textarea.select();

    const execPromise = Promise.resolve().then(() => document.execCommand('copy'));
    const success = await execPromise
        .catch((error) => {
            let errorMessage = String(error);
            if (error && typeof error.message === 'string') {
                errorMessage = error.message;
            }
            Logger.logDebug('Clipboard fallback threw an error', {
                error: errorMessage
            }, Logger.LogCategory.EVENT);
            return false;
        })
        .finally(() => {
            body.removeChild(textarea);
        });

    if (!success) {
        Logger.logDebug('Clipboard fallback copy failed', {
            valueLength: text.length
        }, Logger.LogCategory.EVENT);
        return;
    }

    triggerCopyFeedback(valueElement, feedbackClass);
}

function triggerCopyFeedback(valueElement, feedbackClass) {
    if (!valueElement || !valueElement.classList) {
        return;
    }
    if (typeof feedbackClass !== 'string' || feedbackClass === '') {
        return;
    }

    if (!document.body.contains(valueElement)) {
        return;
    }

    const existingTimer = copyFeedbackTimers.get(valueElement);
    if (existingTimer) {
        window.clearTimeout(existingTimer);
    }

    const alreadyAnimating = valueElement.classList.contains(feedbackClass);
    if (!alreadyAnimating) {
        valueElement.classList.remove(feedbackClass);
        void valueElement.offsetWidth;
        valueElement.classList.add(feedbackClass);
    }

    const timer = window.setTimeout(() => {
        valueElement.classList.remove(feedbackClass);
    }, 700);
    copyFeedbackTimers.set(valueElement, timer);
}

function handleCollapseToggleInteraction(event, collapseToggle, interactionSource) {
    if (!collapseToggle) {
        throw new Error('handleCollapseToggleInteraction called without target collapse toggle');
    }

    if (event.clientX === undefined || event.clientY === undefined) {
        throw new Error(`Invalid MouseEvent: missing coordinates (type: ${event.type})`);
    }

    const noteElement = collapseToggle.closest('.note');
    if (!noteElement) {
        throw new Error('Collapse toggle activated without parent .note element');
    }

    const noteId = noteElement.dataset?.noteId;
    if (!noteId) {
        throw new Error('Collapse toggle activated without a parent note id');
    }

    const coordinates = {
        x: event.clientX,
        y: event.clientY
    };

    const isCurrentlyCollapsed = noteElement.dataset.isCollapsed === 'true';
    const canCollapse = noteElement.dataset.canCollapse !== 'false';

    Logger.logDebug(
        interactionSource === 'mousedown' ? 'Collapse toggle pressed' : 'Collapse toggle clicked',
        {
            noteId,
            isCurrentlyCollapsed,
            canCollapse,
            coordinates
        },
        Logger.LogCategory.EVENT
    );

    const searchInput = document.getElementById('search-input');
    if (searchInput && typeof searchInput.blur === 'function') {
        searchInput.blur();
    }
    if (ModeContext.isSearching) {
        actionExitSearchMode();
    }

    event.preventDefault();
    event.stopPropagation();

	if (isCurrentlyCollapsed) {
		void CommandGate.run('mouse.expand_note', async () => {
			await expandNote(noteId);
		});
		return;
	}

	if (canCollapse) {
		void CommandGate.run('mouse.collapse_note', async () => {
			await collapseNote(noteId);
		});
		return;
	}

    Logger.logNoop('Collapse toggle ignored: note cannot collapse', {
        noteId
    });
}

function handleMouseOver(event) {
    if (!event) {
        throw new Error('handleMouseOver called without an event object');
    }

    const target = event.target;
    if (!target) {
        throw new Error('Mouseover event missing target element');
    }

    const noteElement = target.closest('.note');
    if (!noteElement) {
        return;
    }

    const noteId = noteElement.dataset.noteId;
    if (!noteId) {
        throw new Error('Note element missing data-note-id attribute in handleMouseOver');
    }

    if (ModeContext.hoveredNoteId === noteId) {
        return;
    }

    ModeContext.setHoveredNoteId(noteId);

    Logger.logDebug('Pointer entered note', {
        noteId,
        isEditing: ModeContext.isEditing
    }, Logger.LogCategory.EVENT);
}

function handleMouseOut(event) {
    if (!event) {
        throw new Error('handleMouseOut called without an event object');
    }

    const target = event.target;
    if (!target) {
        throw new Error('Mouseout event missing target element');
    }

    const noteElement = target.closest('.note');
    if (!noteElement) {
        return;
    }

    const noteId = noteElement.dataset.noteId;
    if (!noteId) {
        throw new Error('Note element missing data-note-id attribute in handleMouseOut');
    }

    const relatedTarget = event.relatedTarget;
    if (relatedTarget && noteElement.contains(relatedTarget)) {
        return;
    }

    if (ModeContext.hoveredNoteId !== noteId) {
        return;
    }

    ModeContext.setHoveredNoteId(null);

    Logger.logDebug('Pointer left note', {
        noteId
    }, Logger.LogCategory.EVENT);
}
