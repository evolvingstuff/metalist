import { CONFIG } from './config.js';

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
        return noteElement.dataset.id;
    },

    /**
     * Make a note editable/non-editable
     */
    setNoteEditable(noteElement, isEditable) {
        const content = this.getNoteContent(noteElement);
        content.contentEditable = isEditable.toString();
        noteElement.classList.toggle(CONFIG.CLASSES.EDITING, isEditable);
    },

    /**
     * Save cursor position for a content element
     *
     * TODO: why is this function not used??
     */
    saveCursorPosition(contentElement) {
        const selection = window.getSelection();
        const range = selection.getRangeAt(0);
        return {
            range: range.cloneRange(),
            start: range.startOffset,
            end: range.endOffset
        };
    },

    /**
     * Restore cursor position for a content element
     */
    restoreCursorPosition(contentElement, position) {
        if (!position) return;

        const selection = window.getSelection();
        selection.removeAllRanges();
        selection.addRange(position.range);
    },

    /**
     * Get the current content of a note
     */
    getNoteContentText(noteElement) {
        const content = this.getNoteContent(noteElement);
        return content.innerHTML.trim();
    },

    /**
     * Check if element is a note content element
     */
    isNoteContent(element) {
        return element.classList.contains(CONFIG.CLASSES.NOTE_CONTENT);
    },

    /**
     * Get current cursor position in a note
     */
    getCursorPosition(noteElement) {
        const contentElement = this.getNoteContent(noteElement);
        const selection = window.getSelection();
        if (!selection.rangeCount) {
            console.log('No selection range found');
            return null;
        }

        const range = selection.getRangeAt(0);
        if (!contentElement.contains(range.commonAncestorContainer)) {
            console.log('Selection not in content element');
            return null;
        }

        const position = {
            offset: range.startOffset,
            path: this.getNodePath(range.startContainer, contentElement)
        };
        
        console.log('Stored cursor position:', position);
        return position;
    },

    /**
     * Get path to a node relative to its ancestor
     */
    getNodePath(node, ancestor) {
        const path = [];
        let current = node;
        
        while (current !== ancestor && current.parentNode) {
            const parent = current.parentNode;
            const children = Array.from(parent.childNodes);
            path.unshift(children.indexOf(current));
            current = parent;
        }
        
        return path;
    },

    /**
     * Restore cursor to a specific position
     */
    setCursorPosition(noteElement, position) {
        console.log('Attempting to restore cursor position:', position);
        
        if (!position || position === 'end') {
            console.log('No position or "end" specified, focusing at end');
            this.focusNote(noteElement);
            return;
        }

        const contentElement = this.getNoteContent(noteElement);
        let node = contentElement;
        
        // Follow the path to find the target node
        for (const index of position.path) {
            console.log('Following path index:', index);
            if (node.childNodes[index]) {
                node = node.childNodes[index];
            } else {
                console.log('Path invalid, falling back to end');
                this.focusNote(noteElement);
                return;
            }
        }

        try {
            const range = document.createRange();
            const selection = window.getSelection();
            
            range.setStart(node, position.offset);
            range.collapse(true);
            selection.removeAllRanges();
            selection.addRange(range);
            contentElement.focus();
            console.log('Successfully restored cursor position');
        } catch (e) {
            console.error('Failed to set cursor position:', e);
            this.focusNote(noteElement);
        }
    },

    /**
     * Get all notes on the page
     */
    getAllNotes() {
        return document.querySelectorAll(`.${CONFIG.CLASSES.NOTE}`);
    },

    /**
     * Focus a note's content and place cursor at the end
     */
    focusNote(noteElement) {
        const content = this.getNoteContent(noteElement);
        content.focus();

        // Place cursor at the end
        const range = document.createRange();
        const selection = window.getSelection();
        range.selectNodeContents(content);
        range.collapse(false); // false = collapse to end
        selection.removeAllRanges();
        selection.addRange(range);
    }
}; 