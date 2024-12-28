import { CONFIG } from './config.js';
import { NotesAPI } from './api-client.js';
import { DOMUtils } from './dom-utils.js';
import { NoteState } from './note-state.js';
import { setupKeyboardShortcuts } from '../shortcuts.js';
import { NoteStateMachine } from './note-state-machine.js';

/**
 * IMPORTANT ASSUMPTIONS AND GOTCHAS:
 * 
 * 1. Event Order:
 *    - Events might fire during state transitions
 *    - Click and blur events must coordinate for proper state changes
 *    - Focus management depends on event order
 * 
 * 2. State Machine Interaction:
 *    - Events trigger state transitions via NoteState
 *    - Direct state machine calls only for idle transitions
 *    - Search blur handler manages search → editing transition
 * 
 * 3. Cursor Position:
 *    - Click events preserve natural cursor position
 *    - Programmatic focus may override cursor position
 *    - Search → Edit transition must preserve click position
 * 
 * 4. Event Cleanup:
 *    - State transitions might remove elements
 *    - Event listeners must check element validity
 *    - Async handlers must verify state before acting
 */

/**
 * Handles DOM events and coordinates with state machine
 */
export const EventHandlers = {
    init() {
        // Global event listeners
        document.addEventListener('click', this.handleClick.bind(this));
        document.addEventListener('input', this.handleInput.bind(this));
        document.addEventListener('blur', this.handleBlur.bind(this), true);
        document.addEventListener('paste', this.handlePaste.bind(this));
        document.addEventListener('dragstart', this.handleDragStart.bind(this));
        document.addEventListener('dragover', this.handleDragOver.bind(this));
        document.addEventListener('drop', this.handleDrop.bind(this));
        document.addEventListener('dragend', this.handleDragEnd.bind(this));
        
        // Add button setup
        const addButton = document.querySelector('.add-note');
        if (addButton) {
            addButton.addEventListener('click', () => NotesAPI.createNote());
            addButton.addEventListener('dragstart', this.handleAddButtonDragStart.bind(this));
        }

        // Trash can setup
        const trashCan = document.getElementById('trash-can');
        if (trashCan) {
            trashCan.addEventListener('dragover', this.handleTrashDragOver.bind(this));
            trashCan.addEventListener('drop', this.handleTrashDrop.bind(this));
            trashCan.addEventListener('dragleave', this.handleTrashDragLeave.bind(this));
        }

        // Set up keyboard shortcuts
        setupKeyboardShortcuts({
            stopEditing: () => {
                if (NoteStateMachine.state === 'editing') {
                    NoteStateMachine.transition('idle');
                }
            },
            addSibling: async () => {
                if (NoteStateMachine.state === 'editing') {
                    const currentNote = NoteStateMachine.data.currentNote;
                    await NotesAPI.createSibling(DOMUtils.getNoteId(currentNote));
                }
            },
            addChild: async () => {
                if (NoteStateMachine.state === 'editing') {
                    const currentNote = NoteStateMachine.data.currentNote;
                    await NotesAPI.createChild(DOMUtils.getNoteId(currentNote));
                }
            },
            addTop: async () => {
                if (NoteStateMachine.state !== 'editing') {
                    await NotesAPI.createNote();
                }
            },
            undo: () => NotesAPI.undo(),
            redo: () => NotesAPI.redo(),
            moveUp: async () => {
                if (NoteStateMachine.state === 'editing') {
                    const currentNote = NoteStateMachine.data.currentNote;
                    await NotesAPI.moveNoteUp(DOMUtils.getNoteId(currentNote));
                }
            },
            moveDown: async () => {
                if (NoteStateMachine.state === 'editing') {
                    const currentNote = NoteStateMachine.data.currentNote;
                    await NotesAPI.moveNoteDown(DOMUtils.getNoteId(currentNote));
                }
            }
        });

        this.initSearchHandlers();
    },

    /**
     * Handle click events
     */
    handleClick(event) {
        console.log('👆 CLICK EVENT:', {
            target: {
                element: event.target?.className,
                isNoteContent: DOMUtils.isNoteContent(event.target)
            },
            currentState: NoteStateMachine.state,
            activeElement: document.activeElement?.className,
            stack: new Error().stack
        });

        const noteElement = DOMUtils.findNoteElement(event.target);
        if (noteElement && DOMUtils.isNoteContent(event.target)) {
            console.log('🖱 Note state:', {
                pristine: {
                    classList: [...event.target.classList],
                    contentEditable: event.target.contentEditable,
                    attributes: [...event.target.attributes].map(a => `${a.name}="${a.value}"`),
                },
                parent: {
                    classList: [...noteElement.classList],
                    attributes: [...noteElement.attributes].map(a => `${a.name}="${a.value}"`)
                }
            });
            
            // If we're in search mode, let the blur handler handle it
            if (NoteStateMachine.state === 'searching') {
                return;
            }
            
            // Direct transition if already editing
            if (NoteStateMachine.state === 'editing') {
                console.log('   ➡️ Direct edit→edit transition');
                NoteStateMachine.transition('editing', {
                    currentNote: noteElement,
                    lastSavedContent: DOMUtils.getNoteContentText(noteElement)
                });
                return;
            }
            
            console.log('   ⚪ Going through NoteState.startEditing');
            NoteState.startEditing(noteElement);
        }
    },

    /**
     * Handle input events
     */
    handleInput(event) {
        if (DOMUtils.isNoteContent(event.target)) {
            NoteState.handleContentChange();
        }
    },

    /**
     * Handle blur events
     */
    handleBlur(event) {
        // Only handle blur for note content
        if (!DOMUtils.isNoteContent(event.target)) {
            console.log('🌟 Blur: Ignoring - not note content');
            return;
        }

        const noteElement = DOMUtils.findNoteElement(event.target);
        if (!noteElement) {
            console.log('🌟 Blur: Ignoring - no note element');
            return;
        }

        // If clicking within any note content or search, don't exit edit mode
        if ((event.relatedTarget && DOMUtils.isNoteContent(event.relatedTarget)) || 
            event.relatedTarget?.id === 'search-input') {
            console.log('🌟 Blur: Preserving edit mode - clicking note content or search');
            return;
        }

        console.log('🌟 Blur: Transitioning to idle', {
            from: event.target?.className,
            to: event.relatedTarget?.className,
            currentState: NoteStateMachine.state
        });
        
        // Only transition to idle if we're not clicking another note's content
        NoteStateMachine.transition('idle');
    },

    /**
     * Initialize search handlers
     */
    initSearchHandlers() {
        const searchInput = document.getElementById('search-input');
        if (!searchInput) return;

        // Enter search mode on focus
        searchInput.addEventListener('focus', async () => {
            const query = searchInput.value;
            await NoteState.startSearch(query);
        });

        // Handle search input
        searchInput.addEventListener('input', async (event) => {
            const query = event.target.value;
            await NoteState.startSearch(query);
        });

        // Handle blur from search - use capture phase
        searchInput.addEventListener('blur', async (event) => {
            console.log('🔍 BLUR EVENT:', {
                relatedTarget: event.relatedTarget?.className,
                activeElement: document.activeElement?.className,
                currentState: NoteStateMachine.state
            });
            // If clicking a note, transition directly to editing
            if (event.relatedTarget?.closest('.note')) {
                event.stopImmediatePropagation();  // Stop ALL other handlers
                event.preventDefault();
                
                const noteElement = event.relatedTarget.closest('.note');
                // Direct transition from search → edit
                await NoteStateMachine.transition('editing', {
                    currentNote: noteElement,
                    lastSavedContent: DOMUtils.getNoteContentText(noteElement)
                });
                return;
            }
            // Only go to idle if not clicking a note
            NoteStateMachine.transition('idle');
        }, true);  // true = use capture phase

        // Global click handler
        document.addEventListener('click', (event) => {
            console.log('🖱️ CLICK EVENT:', {
                target: event.target?.className,
                activeElement: document.activeElement?.className,
                currentState: NoteStateMachine.state
            });
        }, true);
    },

    /**
     * Handle paste events
     */
    async handlePaste(event) {
        const noteElement = DOMUtils.findNoteElement(event.target);
        if (!noteElement || !DOMUtils.isNoteContent(event.target)) return;

        const items = (event.clipboardData || event.originalEvent.clipboardData).items;
        for (const item of items) {
            if (item.type.indexOf('image') === 0) {
                event.preventDefault();
                await this.handleImagePaste(item, noteElement);
            }
        }
    },

    /**
     * Handle image paste
     */
    async handleImagePaste(item, noteElement) {
        const blob = item.getAsFile();
        const reader = new FileReader();
        
        reader.onload = async (event) => {
            const img = document.createElement('img');
            img.src = event.target.result;
            img.style.maxWidth = '100%';
            
            const selection = window.getSelection();
            const range = selection.getRangeAt(0);
            range.deleteContents();
            range.insertNode(img);
            
            await NoteState.saveCurrentNote();
        };
        
        reader.readAsDataURL(blob);
    },

    handleDragStart(event) {
        const noteElement = DOMUtils.findNoteElement(event.target);
        if (!noteElement || !event.target.classList.contains('drag-handle')) return;
        
        noteElement.classList.add(CONFIG.CLASSES.DRAGGING);
        event.dataTransfer.setData('text/plain', DOMUtils.getNoteId(noteElement));
        event.dataTransfer.effectAllowed = 'move';
    },

    getValidDropPosition(draggingElement, targetElement, event) {
        if (!draggingElement || !targetElement) return null;
        
        // Can't drop on itself
        if (draggingElement === targetElement) return null;
        
        // Can't drop on a descendant
        if (DOMUtils.isDescendant(targetElement, draggingElement)) return null;
        
        // Calculate position relative to target
        const rect = targetElement.getBoundingClientRect();
        const relativeY = event.clientY - rect.top;
        const relativeX = event.clientX - rect.left;
        const threshold = rect.height / 2;  // 1/3
        const horizontalMidpoint = rect.width / 2;

        // Check if the dragged element is immediately before or after the target
        const isNextSibling = draggingElement.nextElementSibling === targetElement;
        const isPrevSibling = draggingElement.previousElementSibling === targetElement;

        // Get parent note of target
        const targetParentNote = DOMUtils.findNoteElement(targetElement.parentElement);
        
        // Can't drop into your own parent (but can drop before/after it)
        const draggedParentNote = DOMUtils.findNoteElement(draggingElement.parentElement);
        if (draggedParentNote === targetElement && relativeX > horizontalMidpoint) {
            return null;
        }

        // Determine valid drop position based on location
        if (relativeX > horizontalMidpoint) {
            return 'inside';
        } else if (relativeY < threshold && !isNextSibling) {
            return 'before';
        } else if (relativeY > rect.height - threshold && !isPrevSibling) {
            return 'after';
        }

        return null;
    },

    handleDragOver(event) {
        event.preventDefault();
        const noteElement = DOMUtils.findNoteElement(event.target);
        if (!noteElement) {
            // Clear all drag indicators if we're not over a note
            document.querySelectorAll(`.${CONFIG.CLASSES.NOTE}`).forEach(note => {
                note.classList.remove(
                    CONFIG.CLASSES.DRAG_BEFORE,
                    CONFIG.CLASSES.DRAG_AFTER,
                    CONFIG.CLASSES.DRAG_INSIDE
                );
            });
            return;
        }

        const draggingElement = document.querySelector(`.${CONFIG.CLASSES.DRAGGING}`);
        
        // Clear previous drag indicators
        document.querySelectorAll(`.${CONFIG.CLASSES.NOTE}`).forEach(note => {
            if (note !== noteElement) {
                note.classList.remove(
                    CONFIG.CLASSES.DRAG_BEFORE,
                    CONFIG.CLASSES.DRAG_AFTER,
                    CONFIG.CLASSES.DRAG_INSIDE
                );
            }
        });

        // Remove all indicators from current note
        noteElement.classList.remove(CONFIG.CLASSES.DRAG_BEFORE, CONFIG.CLASSES.DRAG_AFTER, CONFIG.CLASSES.DRAG_INSIDE);
        
        // Get valid drop position and show corresponding indicator
        const dropPosition = this.getValidDropPosition(draggingElement, noteElement, event);
        if (dropPosition) {
            noteElement.classList.add(CONFIG.CLASSES[`DRAG_${dropPosition.toUpperCase()}`]);
        }
    },

    handleDragLeave(event) {
        // Only clear indicators if we've actually left a note
        // (not just moved between child elements)
        const relatedTarget = event.relatedTarget;
        const currentNoteElement = DOMUtils.findNoteElement(event.target);
        const newNoteElement = relatedTarget ? DOMUtils.findNoteElement(relatedTarget) : null;

        if (currentNoteElement && (!newNoteElement || currentNoteElement !== newNoteElement)) {
            currentNoteElement.classList.remove(
                CONFIG.CLASSES.DRAG_BEFORE,
                CONFIG.CLASSES.DRAG_AFTER,
                CONFIG.CLASSES.DRAG_INSIDE
            );
        }
    },

    handleDrop(event) {
        event.preventDefault();
        const noteElement = DOMUtils.findNoteElement(event.target);
        if (!noteElement) return;

        const draggedId = event.dataTransfer.getData('text/plain');
        const draggingElement = document.querySelector(`.${CONFIG.CLASSES.DRAGGING}`);
        
        // Get valid drop position
        const dropPosition = this.getValidDropPosition(draggingElement, noteElement, event);
        if (!dropPosition) {
            // Clean up and return early if invalid
            if (draggingElement) {
                draggingElement.classList.remove(CONFIG.CLASSES.DRAGGING);
            }
            return;
        }

        // Handle dropping from add button
        if (draggedId === 'new-note') {
            let position = null;
            let siblingId = null;

            if (noteElement.classList.contains(CONFIG.CLASSES.DRAG_BEFORE)) {
                position = 'BEFORE';
                siblingId = DOMUtils.getNoteId(noteElement);
            } else if (noteElement.classList.contains(CONFIG.CLASSES.DRAG_AFTER)) {
                position = 'AFTER';
                siblingId = DOMUtils.getNoteId(noteElement);
            }

            const newParentId = noteElement.classList.contains(CONFIG.CLASSES.DRAG_INSIDE) 
                ? DOMUtils.getNoteId(noteElement) 
                : noteElement.dataset.parentId || null;

            NotesAPI.createNoteDrop(newParentId, siblingId, position);
        } else {
            // Handle moving existing notes
            let position = null;
            let siblingId = null;

            if (noteElement.classList.contains(CONFIG.CLASSES.DRAG_BEFORE)) {
                position = 'BEFORE';
                siblingId = DOMUtils.getNoteId(noteElement);
            } else if (noteElement.classList.contains(CONFIG.CLASSES.DRAG_AFTER)) {
                position = 'AFTER';
                siblingId = DOMUtils.getNoteId(noteElement);
            }

            const newParentId = noteElement.classList.contains(CONFIG.CLASSES.DRAG_INSIDE) 
                ? DOMUtils.getNoteId(noteElement) 
                : noteElement.dataset.parentId || null;

            NotesAPI.moveNote(draggedId, siblingId, position, newParentId)
                .catch(error => {
                    console.error('Error moving note:', error);
                });
        }

        // Clean up drag classes
        if (draggingElement) {
            draggingElement.classList.remove(CONFIG.CLASSES.DRAGGING);
        }
        
        // Remove all drag-related classes
        document.querySelectorAll(`.${CONFIG.CLASSES.NOTE}`).forEach(note => {
            note.classList.remove(
                CONFIG.CLASSES.DRAG_BEFORE,
                CONFIG.CLASSES.DRAG_AFTER,
                CONFIG.CLASSES.DRAG_INSIDE
            );
        });
    },

    handleDragEnd(event) {
        const draggingElement = document.querySelector(`.${CONFIG.CLASSES.DRAGGING}`);
        if (draggingElement) {
            draggingElement.classList.remove(CONFIG.CLASSES.DRAGGING);
        }
        
        // Remove all drag-related classes
        document.querySelectorAll(`.${CONFIG.CLASSES.NOTE}`).forEach(note => {
            note.classList.remove(
                CONFIG.CLASSES.DRAG_BEFORE,
                CONFIG.CLASSES.DRAG_AFTER,
                CONFIG.CLASSES.DRAG_INSIDE
            );
        });
    },

    // Add these new methods to handle add button drag and drop
    handleAddButtonDragStart(event) {
        // Only allow dragging if there's at least one note
        const hasNotes = document.querySelector(`.${CONFIG.CLASSES.NOTE}`) !== null;
        if (!hasNotes) {
            event.preventDefault();
            return;
        }
        
        event.dataTransfer.setData('text/plain', 'new-note');
        event.dataTransfer.effectAllowed = 'copy';
    },

    // Add these new methods to handle trash can functionality
    handleTrashDragOver(event) {
        event.preventDefault();
        event.currentTarget.classList.add('trash-hover');
        
        // Add red border to the dragged note
        const draggingElement = document.querySelector(`.${CONFIG.CLASSES.DRAGGING}`);
        if (draggingElement) {
            draggingElement.classList.add('drag-trash');
        }
    },

    handleTrashDragLeave(event) {
        event.currentTarget.classList.remove('trash-hover');
        
        // Remove red border from the dragged note
        const draggingElement = document.querySelector(`.${CONFIG.CLASSES.DRAGGING}`);
        if (draggingElement) {
            draggingElement.classList.remove('drag-trash');
        }
    },

    handleTrashDrop(event) {
        event.preventDefault();
        event.currentTarget.classList.remove('trash-hover');
        
        const draggedId = event.dataTransfer.getData('text/plain');
        if (draggedId && draggedId !== 'new-note') {
            // Remove the drag-trash class before deleting
            const draggingElement = document.querySelector(`.${CONFIG.CLASSES.DRAGGING}`);
            if (draggingElement) {
                draggingElement.classList.remove('drag-trash');
            }
            NotesAPI.deleteNote(draggedId);
        }
    }
}; 