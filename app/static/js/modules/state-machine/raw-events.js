import { DOMUtils } from '../dom-utils.js';
import { StateContext } from './state-context.js';

/**
 * Raw Event Handlers
 * 
 * Converts DOM events into StateContext objects.
 * Handles initial event processing and data extraction.
 * 
 * Each handler:
 * 1. Receives DOM event
 * 2. Extracts relevant data
 * 3. Returns StateContext with:
 *    - type: Event type (e.g. 'NOTE_CONTENT_CLICKED')
 *    - Any other relevant fields (e.g. noteId, content, coordinates)
 * 
 * @example
 * // Convert click to StateContext
 * handleAddNoteClick(event) {
 *   return new StateContext().setType('ADD_BUTTON_CLICKED');
 * }
 */
export const RawEvents = {

    handleClick(domEvent) {
        // NO MERCY validation
        if (!domEvent) {
            throw new Error('Click missing event');
        }
        if (!domEvent.target) {
            throw new Error('Click event missing target');
        }

        // Get click coordinates
        const clickInfo = {
            x: domEvent.clientX,
            y: domEvent.clientY
        };

        // Handle click based on target
        if (DOMUtils.isNoteContent(domEvent.target)) {
            return this.handleNoteContentClick(domEvent);  // Let handleNoteContentClick handle click info
        }
        if (domEvent.target?.classList?.contains('search-input')) {
            return this.handleSearchClick(domEvent);
        }
        if (domEvent.target?.classList?.contains('add-note')) {
            return this.handleAddNoteClick(domEvent);
        }
        if (domEvent.target?.classList?.contains('menu-button')) {
            return this.handleMenuClick(domEvent);
        }
        if (domEvent.target?.classList?.contains('trash-can')) {
            return this.handleTrashCanClick(domEvent);
        }
        if (domEvent.target?.classList?.contains('interactive')) {
            return this.handleInteractiveClick(domEvent);
        }

        // Check if click is inside a note
        const noteElement = DOMUtils.findNoteElement(domEvent.target);
        if (noteElement) {
            return this.handleNoteClick(domEvent);
        }

        // Non-interactive click outside any note
        return this.handleClickOutsideNote(domEvent);
    },

    handleNoteContentClick(domEvent) {
        // NO MERCY - validate event
        if (!domEvent) {
            throw new Error('Note content click missing event');
        }
        if (!domEvent.target) {
            throw new Error('Note content click event missing target');
        }
        if (typeof domEvent.clientX !== 'number' || typeof domEvent.clientY !== 'number') {
            throw new Error('Click event missing coordinates');
        }

        // Get note element and ID
        const noteElement = DOMUtils.findNoteElement(domEvent.target);
        if (!noteElement) {
            throw new Error('Click not in note');
        }
        const noteId = DOMUtils.getNoteId(noteElement);
        if (!noteId) {
            throw new Error('Note missing ID');
        }

        console.log('🎯 Note content click:', {
            target: domEvent.target,
            classList: domEvent.target?.classList?.toString(),
            nodeType: domEvent.target?.nodeType,
            nodeName: domEvent.target?.nodeName,
            textContent: domEvent.target?.textContent?.slice(0, 20), // First 20 chars
            coordinates: { x: domEvent.clientX, y: domEvent.clientY },
            noteId
        });

        const content = DOMUtils.getNoteContentHTMLById(noteId);
        return new StateContext()
            .setType('NOTE_CONTENT_CLICKED')
            .setNoteId(noteId)
            .setCoordinates({ x: domEvent.clientX, y: domEvent.clientY })
            .setLastSavedContent(content);
    },

    handleSearchClick(domEvent) {
        return new StateContext()
            .setType('SEARCH_FOCUSED')
            .setQuery(domEvent.target.value);
    },

    handleAddNoteClick(domEvent) {
        return new StateContext().setType('ADD_BUTTON_CLICKED');
    },

    handleMenuClick(domEvent) {
        alert('TODO: Implement menu handling');
        return new StateContext().setType('NO_OP');
    },

    handleTrashCanClick(domEvent) {
        alert('TODO: Implement trash can handling');
        return new StateContext().setType('NO_OP');
    },

    handleKeyDown(domEvent) {
        return new StateContext()
            .setType('KEY_DOWN')
            .setKey(domEvent.key)
            .setMetaKey(domEvent.metaKey || domEvent.ctrlKey)
            .setShiftKey(domEvent.shiftKey);
    },

    handleDragStart(domEvent) {
        // NO MERCY validation
        if (!domEvent) {
            throw new Error('Drag start missing event');
        }
        if (!domEvent.target) {
            throw new Error('Drag start event missing target');
        }

        const noteElement = DOMUtils.findNoteElement(domEvent.target);
        if (!noteElement) {
            throw new Error('Drag start not in note');
        }

        const noteId = DOMUtils.getNoteId(noteElement);
        if (!noteId) {
            throw new Error('Note missing ID');
        }

        return new StateContext()
            .setType('DRAG_STARTED')
            .setNoteId(noteId);
    },

    handleInput(domEvent) {
        if (DOMUtils.isNoteContent(domEvent.target)) {
            const noteElement = DOMUtils.findNoteElement(domEvent.target);
            if (!noteElement) {
                throw new Error('Could not find parent note element');
            }

            const noteId = DOMUtils.getNoteId(noteElement);
            if (!noteId) {
                throw new Error('Note element missing ID');
            }

            const content = DOMUtils.getNoteContentHTML(noteElement);
            return new StateContext()
                .setType('NOTE_CONTENT_CHANGED')
                .setNoteId(noteId)
                .setContent(content);
        }
        return new StateContext().setType('NO_OP');
    },

    handleSearchInput(domEvent) {
        return new StateContext()
            .setType('SEARCH_QUERY_CHANGED')
            .setQuery(domEvent.target.value);
    },

    handleSearchBlur(domEvent) {
        // If we blurred to a note, get its ID
        const noteElement = domEvent.relatedTarget ? DOMUtils.findNoteElement(domEvent.relatedTarget) : null;
        const noteId = noteElement ? DOMUtils.getNoteId(noteElement) : null;
        
        return new StateContext()
            .setType('SEARCH_BLURRED')
            .setNoteId(noteId);  // Will be null if not clicked on note
    },

    handleClickOutsideNote(domEvent) {
        if (!domEvent) {
            throw new Error('Click outside note missing event');
        }
        return new StateContext()
            .setType('CLICKED_OUTSIDE_NOTE')
            .setCoordinates({ x: domEvent.clientX, y: domEvent.clientY });
    },

    handleFragmentLoaded(domEvent) {
        return new StateContext().setType('FRAGMENT_LOADED');
    },

    handleInteractiveClick(domEvent) {
        return new StateContext()
            .setType('NO_OP')
            .setCoordinates({ x: domEvent.clientX, y: domEvent.clientY });
    },

    handleNoteClick(domEvent) {
        return new StateContext()
            .setType('NO_OP')
            .setCoordinates({ x: domEvent.clientX, y: domEvent.clientY });
    }
}; 