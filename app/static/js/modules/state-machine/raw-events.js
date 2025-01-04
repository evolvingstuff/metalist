import { DOMUtils } from '../dom-utils.js';

/**
 * Maps raw DOM events to low-level semantic events
 * No state awareness, pure event translation
 */
export const RawEvents = {
    handleClick(event) {
        const noteElement = DOMUtils.findNoteElement(event.target);
        const isClickingNoteContent = DOMUtils.isNoteContent(event.target);
        
        if (noteElement && isClickingNoteContent) {
            return {
                type: 'NOTE_CONTENT_CLICKED',
                noteElement,
                position: DOMUtils.getClickPosition(event)
            };
        }

        if (!isClickingNoteContent) {
            return {
                type: 'CLICKED_OUTSIDE_NOTE',
                target: event.target
            };
        }
    },

    handleKeyDown(event) {
        if (event.key === 'Escape') {
            return { type: 'ESCAPE_PRESSED' };
        }

        if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
            return {
                type: 'COMMAND_ENTER_PRESSED',
                shift: event.shiftKey
            };
        }

        if (event.key.startsWith('Arrow') && (event.metaKey || event.ctrlKey)) {
            return {
                type: 'COMMAND_ARROW_PRESSED',
                direction: event.key.replace('Arrow', '').toLowerCase()
            };
        }
    },

    handleDragStart(event) {
        const noteElement = DOMUtils.findNoteElement(event.target);
        if (!noteElement) return;

        return {
            type: 'NOTE_DRAG_STARTED',
            noteElement,
            dragEvent: event
        };
    },

    handleInput(event) {
        if (DOMUtils.isNoteContent(event.target)) {
            return {
                type: 'NOTE_CONTENT_CHANGED',
                noteElement: DOMUtils.findNoteElement(event.target),
                content: DOMUtils.getNoteContentText(event.target)
            };
        }
    },

    handleAddButtonClick(event) {
        return {
            type: 'ADD_BUTTON_CLICKED'
        };
    },

    handleSearchFocus(event) {
        return {
            type: 'SEARCH_FOCUSED',
            query: event.target.value
        };
    },

    handleSearchInput(event) {
        return {
            type: 'SEARCH_QUERY_CHANGED',
            query: event.target.value
        };
    },

    handleSearchBlur(event) {
        return {
            type: 'SEARCH_BLURRED',
            clickedElement: event.relatedTarget
        };
    }

    // ... other raw event handlers
}; 