import { CONFIG } from './config.js';
import { NotesAPI } from './api-client.js';
import { DOMUtils } from './dom-utils.js';
import { NoteState } from './note-state.js';
import { setupKeyboardShortcuts } from '../shortcuts.js';

/**
 * Manages all event handling for the application
 */
export const EventHandlers = {
    // Track drag state
    draggedNoteId: null,
    dragTarget: null,
    isDraggingAddButton: false,

    /**
     * Initialize all event listeners
     */
    init() {
        // Initialize add button immediately (don't wait for DOMContentLoaded)
        this.initializeAddButton();

        document.addEventListener('DOMContentLoaded', this.handleDOMContentLoaded.bind(this));
        document.addEventListener('click', this.handleClick.bind(this));
        document.addEventListener('input', this.handleInput.bind(this));
        document.addEventListener('blur', this.handleBlur.bind(this), true);
        document.addEventListener('paste', this.handlePaste.bind(this));
        document.addEventListener('keydown', this.handleKeydown.bind(this));

        // Drag and drop events
        document.addEventListener('dragstart', this.handleDragStart.bind(this));
        document.addEventListener('dragover', this.handleDragOver.bind(this));
        document.addEventListener('drop', this.handleDrop.bind(this));
        document.addEventListener('dragend', this.handleDragEnd.bind(this));

        // Setup keyboard shortcuts
        setupKeyboardShortcuts({
            stopEditing: async () => {
                await NoteState.finishEditing();
            }
        });

        if (CONFIG.DEBUG.LOG_STATE_CHANGES) {
            console.log('Event handlers initialized');
        }
    },

    /**
     * Initialize the add button functionality
     */
    initializeAddButton() {
        const addButton = document.querySelector('.add-note');
        if (addButton) {
            console.log('Initializing add button');
            const hasNotes = document.querySelector('.note') !== null;
            addButton.draggable = hasNotes;
            
            addButton.addEventListener('click', async (e) => {
                console.log('Add button clicked');
                try {
                    await NotesAPI.createNote();
                } catch (error) {
                    console.error('Failed to create note:', error);
                }
            });
        } else {
            console.error('Add button not found!');
        }
    },

    /**
     * Handle DOMContentLoaded event
     */
    handleDOMContentLoaded() {
        // Initialize all notes as non-editable
        DOMUtils.getAllNotes().forEach(note => {
            DOMUtils.setNoteEditable(note, false);
        });

        // Initialize drag handles
        this.initializeDragHandles();

        // Verify trash can exists
        if (!document.getElementById('trash-can')) {
            console.error('Trash can not found!');
        }

        // Restore editing state if exists
        this.restoreEditingState();
    },

    /**
     * Initialize drag handles visibility
     */
    initializeDragHandles() {
        DOMUtils.getAllNotes().forEach(note => {
            note.addEventListener('mouseenter', () => {
                DOMUtils.getAllNotes().forEach(n => {
                    const handle = n.querySelector('.drag-handle');
                    if (handle) handle.style.visibility = 'hidden';
                });
                const handle = note.querySelector('.drag-handle');
                if (handle) handle.style.visibility = 'visible';
            });

            note.addEventListener('mouseleave', () => {
                const handle = note.querySelector('.drag-handle');
                if (handle) handle.style.visibility = 'hidden';
            });
        });
    },

    /**
     * Restore editing state from localStorage
     */
    restoreEditingState() {
        const state = JSON.parse(localStorage.getItem('editingState'));
        if (state) {
            const noteElement = document.querySelector(`[data-id="${state.noteId}"]`);
            if (noteElement) {
                NoteState.startEditing(noteElement);
                DOMUtils.restoreCursorPosition(noteElement, state.cursorPosition);
            }
        }

        const newNoteId = localStorage.getItem('newNoteId');
        if (newNoteId) {
            const newNote = document.querySelector(`[data-id="${newNoteId}"]`);
            if (newNote) {
                NoteState.startEditing(newNote);
                localStorage.removeItem('newNoteId');
            }
        }
    },

    /**
     * Handle click events
     */
    handleClick(event) {
        const noteElement = DOMUtils.findNoteElement(event.target);
        if (noteElement && DOMUtils.isNoteContent(event.target)) {
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
        if (DOMUtils.isNoteContent(event.target)) {
            setTimeout(async () => {
                const noteElement = DOMUtils.findNoteElement(event.target);
                if (NoteState.isEditing(noteElement)) {
                    await NoteState.finishEditing();
                }
            }, 0);
        }
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

    /**
     * Handle keyboard events
     */
    async handleKeydown(event) {
        // Create new root note with Enter
        if (event.key === 'Enter') {
            console.log('Enter key pressed');
            // Only if we're not in a contenteditable element
            if (!event.target.isContentEditable) {
                console.log('Creating new note via Enter key');
                try {
                    await NotesAPI.createNote();
                } catch (error) {
                    console.error('Failed to create note:', error);
                }
                return;
            }
        }

        const currentNote = NoteState.getCurrentEditingNote();
        if (!currentNote) return;

        if (event.metaKey) {
            const noteId = DOMUtils.getNoteId(currentNote);

            switch (event.key) {
                case 'Backspace':
                    await NotesAPI.deleteNote(noteId);
                    break;
                    
                case 'ArrowUp':
                    event.preventDefault();
                    await this.handleNoteMove(currentNote, 'prev');
                    break;
                    
                case 'ArrowDown':
                    event.preventDefault();
                    await this.handleNoteMove(currentNote, 'next');
                    break;
                    
                case 'Enter':
                    event.preventDefault();
                    if (event.shiftKey) {
                        await NotesAPI.createChild(noteId);
                    } else {
                        await NotesAPI.createSibling(noteId);
                    }
                    break;
                    
                case 'z':
                    event.preventDefault();
                    await NotesAPI.undo();
                    break;
                    
                case 'y':
                    event.preventDefault();
                    await NotesAPI.redo();
                    break;
            }
        }
    },

    /**
     * Handle note movement
     */
    async handleNoteMove(noteElement, direction) {
        const sibling = direction === 'prev' ? 
            noteElement.previousElementSibling : 
            noteElement.nextElementSibling;
            
        if (sibling) {
            const noteId = DOMUtils.getNoteId(noteElement);
            const siblingId = DOMUtils.getNoteId(sibling);
            
            // Debug: check cursor position before move
            console.log('Cursor position before move:', localStorage.getItem('cursorPosition'));
            
            if (NoteState.isEditing(noteElement)) {
                await NoteState.saveCurrentNote();
            }
            
            await NotesAPI.moveNote(
                noteId, 
                siblingId, 
                direction === 'prev' ? 'BEFORE' : 'AFTER'
            );
        }
    },

    /**
     * Handle drag start
     */
    handleDragStart(event) {
        this.draggedNoteId = null;
        this.isDraggingAddButton = false;
        
        const addButton = event.target.closest('.add-note');
        const dragHandle = event.target.closest('.drag-handle');
        const noteElement = DOMUtils.findNoteElement(event.target);
        
        if (addButton) {
            this.isDraggingAddButton = true;
            this.createDragGhost(event);
        } else if (dragHandle && noteElement) {
            this.draggedNoteId = DOMUtils.getNoteId(noteElement);
            noteElement.classList.add('dragging');
        }
    },

    /**
     * Create drag ghost
     */
    createDragGhost(event) {
        const ghost = document.createElement('div');
        ghost.className = 'note';
        ghost.innerHTML = '<div class="note-content">New note</div>';
        document.body.appendChild(ghost);
        event.dataTransfer.setDragImage(ghost, 0, 0);
        setTimeout(() => document.body.removeChild(ghost), 0);
    },

    /**
     * Handle drag over
     */
    handleDragOver(event) {
        event.preventDefault();
        const hoverNote = DOMUtils.findNoteElement(event.target);
        const trashCan = event.target.closest('#trash-can');
        
        this.clearDragClasses();
        
        if (trashCan) {
            this.handleTrashDragOver(trashCan);
        } else if (hoverNote) {
            this.handleNoteDragOver(event, hoverNote);
        } else {
            this.dragTarget = null;
        }
    },

    /**
     * Handle trash can drag over
     */
    handleTrashDragOver(trashCan) {
        this.dragTarget = trashCan;
        trashCan.classList.add('drag-over');
        
        const draggedElement = document.querySelector(`[data-id="${this.draggedNoteId}"]`);
        if (draggedElement) {
            draggedElement.classList.add('drag-trash');
        }
    },

    /**
     * Handle note drag over
     */
    handleNoteDragOver(event, hoverNote) {
        if (this.isDraggingAddButton) {
            this.handleAddButtonDragOver(event, hoverNote);
        } else if (this.draggedNoteId) {
            const draggedNote = document.querySelector(`[data-id="${this.draggedNoteId}"]`);
            if (this.isValidDrop(draggedNote, hoverNote)) {
                this.updateDropTarget(event, hoverNote);
            }
        }
    },

    /**
     * Handle drop
     */
    async handleDrop(event) {
        event.preventDefault();
        const trashCan = event.target.closest('#trash-can');
        const hoverNote = DOMUtils.findNoteElement(event.target);
        
        if (trashCan && this.draggedNoteId) {
            await NotesAPI.deleteNote(this.draggedNoteId);
        } else if (hoverNote && this.dragTarget) {
            await this.handleNoteDrop(hoverNote);
        }
        
        this.cleanupDragState();
    },

    /**
     * Handle note drop
     */
    async handleNoteDrop(hoverNote) {
        const targetId = DOMUtils.getNoteId(this.dragTarget);
        const isInsideDrop = this.dragTarget.classList.contains('drag-inside');

        if (this.draggedNoteId) {
            if (isInsideDrop) {
                // When dropping inside, only send the new parent
                await NotesAPI.moveNote(this.draggedNoteId, null, null, targetId);
            } else {
                // When dropping before/after a sibling, send sibling and position
                const dropType = this.dragTarget.classList.contains('drag-before') ? 'BEFORE' : 'AFTER';
                await NotesAPI.moveNote(this.draggedNoteId, targetId, dropType);
            }
        } else if (this.isDraggingAddButton) {
            if (isInsideDrop) {
                // Create new note as child
                await NotesAPI.createNoteDrop(targetId, null, null);
            } else {
                // Create new note as sibling
                const dropType = this.dragTarget.classList.contains('drag-before') ? 'BEFORE' : 'AFTER';
                await NotesAPI.createNoteDrop(
                    hoverNote.dataset.parentId || null,
                    targetId,
                    dropType
                );
            }
        }
    },

    /**
     * Get drop type from target classes
     */
    getDropType() {
        if (this.dragTarget.classList.contains('drag-before')) return 'before';
        if (this.dragTarget.classList.contains('drag-after')) return 'after';
        return 'inside';
    },

    /**
     * Handle drag end
     */
    handleDragEnd() {
        this.cleanupDragState();
    },

    /**
     * Clean up drag state
     */
    cleanupDragState() {
        if (this.dragTarget) {
            this.dragTarget.classList.remove('drag-over', 'drag-before', 'drag-after', 'drag-inside');
        }
        const draggedElement = document.querySelector('.dragging');
        if (draggedElement) {
            draggedElement.classList.remove('dragging', 'drag-trash');
        }
        this.dragTarget = null;
        this.draggedNoteId = null;
        this.isDraggingAddButton = false;
    },

    /**
     * Clear drag-related classes
     */
    clearDragClasses() {
        if (this.dragTarget) {
            this.dragTarget.classList.remove('drag-over', 'drag-before', 'drag-after', 'drag-inside');
        }
        const draggedElement = document.querySelector(`[data-id="${this.draggedNoteId}"]`);
        if (draggedElement) {
            draggedElement.classList.remove('drag-trash');
        }
    },

    /**
     * Check if drop is valid
     */
    isValidDrop(draggedElement, targetElement) {
        if (!draggedElement || !targetElement) return false;
        if (draggedElement === targetElement) return false;
        if (targetElement.closest(`[data-id="${draggedElement.dataset.id}"]`)) return false;
        return true;
    },

    /**
     * Update drop target visualization
     */
    updateDropTarget(event, hoverNote) {
        this.dragTarget = hoverNote;
        const rect = hoverNote.getBoundingClientRect();
        const relativeY = event.clientY - rect.top;
        const threshold = rect.height / 3;

        this.dragTarget.classList.remove('drag-before', 'drag-after', 'drag-inside');
        
        if (relativeY < threshold) {
            this.dragTarget.classList.add('drag-before');
        } else if (relativeY > rect.height - threshold) {
            this.dragTarget.classList.add('drag-after');
        } else {
            this.dragTarget.classList.add('drag-inside');
        }
    }
}; 