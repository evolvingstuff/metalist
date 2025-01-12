import { DOMUtils } from '../dom-utils.js';

/**
 * Raw Event Handlers
 * 
 * Converts DOM events into normalized low-level events.
 * Handles initial event processing and data extraction.
 * 
 * Each handler:
 * 1. Receives DOM event
 * 2. Extracts relevant data
 * 3. Returns normalized event object or null
 * 
 * Event Structure:
 * {
 *   type: 'EVENT_TYPE',
 *   ...extracted data
 * }
 * 
 * @example
 * // Convert click to raw event
 * handleAddButtonClick(event) {
 *   return {
 *     type: 'ADD_BUTTON_CLICKED'
 *   };
 * }
 */
export const RawEvents = {
    /**
     * Handle clicks based on target element classes
     */
    handleClick(event) {
        // Log click details
        console.log('Click handler:', {
            target: event.target,
            targetClasses: event.target.classList
        });

        // Check click target type
        if (event.target.classList.contains('note-content')) {
            return this.handleNoteContentClick(event);
        }
        if (event.target.classList.contains('search-input')) {
            return this.handleSearchClick(event);
        }
        if (event.target.classList.contains('add-note')) {
            return this.handleAddNoteClick(event);
        }
        if (event.target.classList.contains('menu-button')) {
            return this.handleMenuClick(event);
        }
        if (event.target.classList.contains('trash-can')) {
            return this.handleTrashCanClick(event);
        }
        if (event.target.classList.contains('interactive')) {
            return { type: 'NO_OP' }; // Other interactive elements
        }

        // Check if click is inside a note
        const noteElement = DOMUtils.findNoteElement(event.target);
        if (noteElement) {
            return { type: 'NO_OP' }; // Click inside note but not on content
        }

        // Non-interactive click outside any note
        return {
            type: 'CLICKED_OUTSIDE_NOTE',
            target: event.target
        };
    },

    /**
     * Handle clicks on note content
     */
    handleNoteContentClick(event) {
        if (!event?.target) {
            throw new Error('Note content click event missing target');
        }

        const noteElement = DOMUtils.findNoteElement(event.target);
        if (!noteElement) {
            throw new Error('Could not find parent note element for click target');
        }

        const noteId = DOMUtils.getNoteId(noteElement);
        if (!noteId) {
            throw new Error('Note element missing ID');
        }

        const position = DOMUtils.getCursorPosition(noteElement);
        console.log('Got cursor position:', position);
        
        return {
            type: 'NOTE_CONTENT_CLICKED',
            noteId,  // Use ID instead of DOM node
            target: event.target,
            position
        };
    },

    /**
     * Handle clicks on search input
     */
    handleSearchClick(event) {
        return {
            type: 'SEARCH_FOCUSED',
            query: event.target.value
        };
    },

    /**
     * Handle clicks on add note button
     */
    handleAddNoteClick() {
        return {
            type: 'ADD_BUTTON_CLICKED'
        };
    },

    /**
     * Handle clicks on menu button
     */
    handleMenuClick() {
        alert('TODO: Implement menu handling');
        return { type: 'NO_OP' }; // TODO: Implement menu handling
    },

    /**
     * Handle clicks on trash can
     */
    handleTrashCanClick() {
        alert('TODO: Implement trash can handling');
        return { type: 'NO_OP' }; // TODO: Implement trash can handling
    },

    handleKeyDown(event) {
        // Just pass through the key information, let states decide what to do
        return {
            type: 'KEY_DOWN',
            key: event.key,
            metaKey: event.metaKey || event.ctrlKey,
            shiftKey: event.shiftKey,
            target: event.target
        };
    },

    handleDragStart(event) {
        const noteElement = DOMUtils.findNoteElement(event.target);
        if (!noteElement) {
            return { type: 'NO_OP' };
        }

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
        return { type: 'NO_OP' };
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
    },

    handleClickOutsideNote(event) {
        return {
            type: 'CLICKED_OUTSIDE_NOTE'
        };
    },

    /**
     * Handle fragment loaded event
     */
    handleFragmentLoaded(event) {
        return {
            type: 'FRAGMENT_LOADED',
            data: event
        };
    },

    // Explicit mapping of event names to handlers
    handleEvent(eventName, event) {
        // Map event names to handlers
        const handlerMap = {
            'Click': this.handleClick.bind(this),
            'KeyDown': this.handleKeyDown.bind(this),
            'DragStart': this.handleDragStart.bind(this),
            'Input': this.handleInput.bind(this),
            'SearchInput': this.handleSearchInput.bind(this),
            'SearchBlur': this.handleSearchBlur.bind(this),
            'SearchFocus': this.handleSearchClick.bind(this),
            'ClickOutsideNote': this.handleClickOutsideNote.bind(this),
            'FragmentLoaded': this.handleFragmentLoaded.bind(this)
        };

        const handler = handlerMap[eventName];
        if (!handler) {
            throw new Error(`No handler for event: ${eventName}`);
        }

        return handler(event);
    }
}; 