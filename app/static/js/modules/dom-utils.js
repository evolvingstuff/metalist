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
     * Set the content of a note
     */
    setNoteContent(noteElement, content) {
        const contentElement = this.getNoteContent(noteElement);
        contentElement.innerHTML = content;
    },

    /**
     * Check if a note is currently being edited
     */
    isNoteEditing(noteElement) {
        return noteElement.classList.contains(CONFIG.CLASSES.EDITING);
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
    },

    /**
     * Check if element is a note content element
     */
    isNoteContent(element) {
        return element.classList.contains(CONFIG.CLASSES.NOTE_CONTENT);
    }
}; 