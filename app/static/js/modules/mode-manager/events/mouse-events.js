import { ModeContextInstance as ModeContext } from '../mode-context.js';
import * as Logger from '../mode-logger.js';
import { createNote, deleteNote, collapseNote, expandNote, moveNoteUp, moveNoteDown, indentNote, outdentNote } from '../actions/note-actions.js';
import { actionSelectNote, actionDeselectNote, actionSwitchNotes } from '../actions/selection-actions.js';
import { actionEnterSearchMode, actionExitSearchMode } from '../actions/search-actions.js';
import { DOMUtils } from '../../dom-utils.js'; 
import { normalizeTagBarForNewTag } from '../services/tag-bar-service.js';
import { CommandGate } from '../services/command-gate-service.js';
import { CommandPalette } from '../../command-palette/command-palette-controller.js';

const collapseToggleClickSkips = new WeakSet();

let selectionDragContext = null;
let ignoreClickAfterSelectionDrag = null;
let moveDragContext = null;
let ignoreClickAfterMoveDrag = null;

const MOVE_DRAG_THRESHOLD_PX = 20;
const MOVE_DRAG_THRESHOLD_SQ = MOVE_DRAG_THRESHOLD_PX * MOVE_DRAG_THRESHOLD_PX;

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

            deleteNote(noteId);
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
            Logger.logNoop('Click on redacted note ignored', {
                noteId,
                reason: 'search_redacted'
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
