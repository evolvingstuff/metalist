import { CONFIG } from './config.js';

/**
 * IMPORTANT ASSUMPTIONS AND GOTCHAS:
 * 
 * 1. Cursor Management:
 *    - setCursorOffset handles both manual and programmatic focus
 *    - focusNote always moves cursor to end
 *    - Position path must account for DOM mutations
 * 
 * 2. Note Structure:
 *    - Notes must maintain expected DOM structure
 *    - Content element must be directly accessible
 *    - Class names defined in CONFIG must exist
 * 
 * 3. Focus Handling:
 *    - Focus operations must be synchronous
 *    - Selection changes must account for content editable
 *    - Path calculations must handle nested structures
 */

/**
 * Utilities for DOM manipulation and traversal
 */
export const DOMUtils = {
    /**
     * Find the closest note element from any child element
     */
    findNoteElement(element) {
        return element.closest(`.${CONFIG.CLASSES.NOTE}`);
    },

    /**
     * Get the content element of a note
     */
    getNoteContent(noteElement) {
        return noteElement.querySelector(`.${CONFIG.CLASSES.NOTE_CONTENT}`);
    },

    /**
     * Get the ID of a note element
     */
    getNoteId(noteElement) {
        if (!noteElement) {
            throw new Error('Note element is required');
        }
        const noteId = noteElement.dataset.noteId;
        if (!noteId) {
            throw new Error('Note missing data-note-id');
        }
        return noteId;
    },

    /**
     * Make a note editable/non-editable
     */
    setNoteEditable(noteElement, isEditable) {
        const content = this.getNoteContent(noteElement);
        if (!content) {
            throw new Error('Note missing content element');
        }
        content.contentEditable = isEditable;
        noteElement.classList.toggle(CONFIG.CLASSES.EDITING, isEditable);
    },

    /**
     * Get a note element by its ID
     */
    getNoteById(noteId) {
        if (!noteId) {
            throw new Error('Note ID is required');
        }
        const note = document.querySelector(`[data-note-id="${noteId}"]`);
        if (!note) {
            throw new Error(`Note not found: ${noteId}`);
        }
        return note;
    },

    /**
     * Get all notes on the page
     */
    getAllNotes() {
        return document.querySelectorAll(`.${CONFIG.CLASSES.NOTE}`);
    },

    /**
     * Focus a note's content and place cursor at end
     */
    focusNote(noteElement) {
        if (!noteElement) {
            throw new Error('Note element is required');
        }
        const content = this.getNoteContent(noteElement);
        if (!content) {
            throw new Error('Note missing content element');
        }
        content.focus();
        this.setCursorOffset(noteElement, content.textContent?.length || 0);
    },

    /**
     * Get cursor offset from start of note
     */
    getCursorOffset(noteElement) {
        if (!noteElement) {
            throw new Error('Note element is required');
        }

        const selection = window.getSelection();
        if (!selection) {
            throw new Error('No selection found');
        }

        const content = this.getNoteContent(noteElement);
        if (!content) {
            throw new Error('Note missing content element');
        }

        if (!content.contains(selection.anchorNode)) {
            throw new Error('Selection not in note');
        }

        // Get path to cursor node
        const path = this.getNodePath(selection.anchorNode, content);
        if (!path) {
            throw new Error('Could not find path to cursor');
        }

        // Calculate offset
        let offset = 0;
        for (const node of path) {
            if (node === selection.anchorNode) {
                offset += selection.anchorOffset;
                break;
            }
            offset += node.textContent?.length || 0;
        }

        return offset;
    },

    /**
     * Set cursor offset in note
     */
    setCursorOffset(noteElement, offset) {
        if (!noteElement) {
            throw new Error('Note element is required');
        }
        if (typeof offset !== 'number' || offset < 0) {
            throw new Error(`Invalid offset: ${offset}`);
        }

        const content = this.getNoteContent(noteElement);
        if (!content) {
            throw new Error('Note missing content element');
        }

        // Find target node and local offset
        let currentOffset = 0;
        let targetNode = null;
        let localOffset = 0;

        const walk = document.createTreeWalker(
            content,
            NodeFilter.SHOW_TEXT,
            null,
            false
        );

        let node;
        while ((node = walk.nextNode())) {
            const length = node.textContent?.length || 0;
            if (currentOffset + length >= offset) {
                targetNode = node;
                localOffset = offset - currentOffset;
                break;
            }
            currentOffset += length;
        }

        if (!targetNode) {
            throw new Error(`Offset ${offset} beyond note content length ${currentOffset}`);
        }

        // Set selection
        const range = document.createRange();
        range.setStart(targetNode, localOffset);
        range.collapse(true);

        const selection = window.getSelection();
        if (!selection) {
            throw new Error('Could not get selection');
        }

        selection.removeAllRanges();
        selection.addRange(range);
    },

    /**
     * Get cursor offset from click coordinates
     */
    getCursorOffsetFromClick(noteElement, coordinates) {
        if (!noteElement) {
            throw new Error('Note element is required');
        }
        if (!coordinates) {
            throw new Error('Coordinates are required');
        }
        if (typeof coordinates.x !== 'number' || typeof coordinates.y !== 'number') {
            throw new Error('Invalid coordinates');
        }

        const range = document.caretRangeFromPoint(coordinates.x, coordinates.y);
        if (!range) {
            throw new Error('Could not create range from click point');
        }

        const content = this.getNoteContent(noteElement);
        if (!content) {
            throw new Error('Note missing content element');
        }

        if (!content.contains(range.startContainer)) {
            throw new Error('Click not in note content');
        }

        // Calculate offset
        let offset = 0;
        const path = this.getNodePath(range.startContainer, content);
        if (!path) {
            throw new Error('Could not find path to clicked node');
        }

        for (const node of path) {
            if (node === range.startContainer) {
                offset += range.startOffset;
                break;
            }
            offset += node.textContent?.length || 0;
        }

        return offset;
    },

    /**
     * Get note content HTML
     */
    getNoteContentHTML(noteElement) {
        const content = this.getNoteContent(noteElement);
        if (!content) {
            throw new Error('Note missing content element');
        }
        return content.innerHTML;
    },

    /**
     * Get note content HTML by ID
     */
    getNoteContentHTMLById(noteId) {
        const noteElement = this.getNoteById(noteId);
        return this.getNoteContentHTML(noteElement);
    },

    /**
     * Get path to a node relative to its ancestor
     */
    getNodePath(node, ancestor) {
        if (!node || !ancestor) {
            return null;
        }

        const path = [];
        let current = node;

        while (current && current !== ancestor) {
            path.unshift(current);
            current = current.parentNode;
        }

        return current === ancestor ? path : null;
    },

    /**
     * Check if element is a note content element
     */
    isNoteContent(element) {
        if (!element) {
            return false;
        }
        return element.classList?.contains(CONFIG.CLASSES.NOTE_CONTENT);
    },

    /**
     * Check if coordinates are within search results panel
     */
    isInSearchResults(coordinates) {
        if (!coordinates || !coordinates.x || !coordinates.y) {
            throw new Error('Valid coordinates required');
        }

        const searchResults = document.querySelector(`.${CONFIG.CLASSES.SEARCH_RESULTS}`);
        if (!searchResults) {
            throw new Error('Search results panel not found');
        }

        const rect = searchResults.getBoundingClientRect();
        return coordinates.x >= rect.left && 
               coordinates.x <= rect.right &&
               coordinates.y >= rect.top && 
               coordinates.y <= rect.bottom;
    },
};