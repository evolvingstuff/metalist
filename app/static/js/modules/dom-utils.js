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
     * Focus a note's content and set cursor position
     * @param {HTMLElement} noteElement - The note element to focus
     * @param {number} cursorOffset - Integer offset from start of content where cursor should be placed
     * @throws {Error} If note content element not found or cursor offset invalid
     */
    focusNote(noteElement, cursorOffset) {
        const contentElement = this.getNoteContent(noteElement);
        if (!contentElement) {
            throw new Error('Note content element not found');
        }
        if (typeof cursorOffset !== 'number' || !Number.isInteger(cursorOffset)) {
            throw new Error('Cursor offset must be an integer');
        }

        // For empty notes, ensure there's a text node
        if (!contentElement.firstChild) {
            contentElement.appendChild(document.createTextNode(''));
        }

        contentElement.focus();
        this.setCursorOffset(noteElement, cursorOffset);
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

        console.log("[DEBUG] Setting cursor at offset:", offset);
        
        // Use the same Range approach for setting position that we use for getting it
        // This ensures consistent cursor behavior
        try {
            // Create new range over all content
            const allTextRange = document.createRange();
            allTextRange.selectNodeContents(content);
            const allText = allTextRange.toString();
            
            // Validate offset is in bounds
            if (offset > allText.length) {
                console.log("[DEBUG] Offset beyond content length, clamping to end");
                offset = allText.length;
            }
            
            // Use Range API to find the right position
            const targetRange = findRangeAtOffset(content, offset);
            if (!targetRange) {
                throw new Error(`Could not find position at offset ${offset}`);
            }
            
            // Set selection
            const selection = window.getSelection();
            if (!selection) {
                throw new Error('Could not get selection');
            }
            
            selection.removeAllRanges();
            selection.addRange(targetRange);
        } catch (error) {
            console.error("[DEBUG] Error setting cursor position:", error);
            throw error;
        }
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

        // Switch approach - directly use the browser's Range object
        const textRange = document.createRange();
        textRange.selectNodeContents(content);
        textRange.setEnd(range.startContainer, range.startOffset);
        const selectedText = textRange.toString();
        offset = selectedText.length;
        
        console.log("[DEBUG] Range-based offset:", offset);
        console.log("[DEBUG] Selected text:", selectedText);
        console.log("[DEBUG] Clicked node:", range.startContainer.nodeName);
        
        // Return the range-based offset which should be more accurate for complex DOM
        return offset;
    },

    /**
     * Get note content HTML
     * @returns {string} The note's content HTML
     * @throws {Error} If note content element is missing or invalid
     */
    getNoteContentHTML(noteElement) {
        if (!noteElement) {
            throw new Error('Note element is required');
        }
        const contentElement = this.getNoteContent(noteElement);
        if (!contentElement) {
            throw new Error('Note missing content element');
        }
        if (!(contentElement instanceof HTMLElement)) {
            throw new Error('Invalid content element type');
        }
        const html = contentElement.innerHTML;
        if (typeof html !== 'string') {
            throw new Error('Note content must be string');
        }
        return html;
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
     * Check if element is a note content element or is inside one
     */
    isNoteContent(element) {
        if (!element) {
            return false;
        }
        // Check if the element itself or any of its parents has the note-content class
        return element.classList?.contains(CONFIG.CLASSES.NOTE_CONTENT) ||
               !!element.closest(`.${CONFIG.CLASSES.NOTE_CONTENT}`);
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

    /**
     * Focus the search input
     */
    focusSearch() {
        const searchInput = document.querySelector(`.${CONFIG.CLASSES.SEARCH_INPUT}`);
        if (!searchInput) {
            throw new Error('Search input not found');
        }
        searchInput.focus();
    },
};

// Helper function to find a range at a specific character offset
// Returns a collapsed range at the specified offset
function findRangeAtOffset(container, targetOffset) {
    // Use a TreeWalker to navigate text nodes
    const walker = document.createTreeWalker(
        container,
        NodeFilter.SHOW_TEXT,
        null,
        false
    );
    
    let currentOffset = 0;
    let node = walker.nextNode();
    
    // Walk through text nodes until we find our target position
    while (node) {
        const nodeLength = node.length;
        
        // If target is within this node
        if (currentOffset + nodeLength >= targetOffset) {
            const range = document.createRange();
            range.setStart(node, targetOffset - currentOffset);
            range.collapse(true);
            return range;
        }
        
        // Move to next node
        currentOffset += nodeLength;
        node = walker.nextNode();
    }
    
    // If we can't find exact position, return range at the end
    const range = document.createRange();
    range.selectNodeContents(container);
    range.collapse(false);
    return range;
}