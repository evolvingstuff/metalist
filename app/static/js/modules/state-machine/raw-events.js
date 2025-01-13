import { DOMUtils } from '../dom-utils.js';
import { StateContext } from './state-context.js';

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
     * NO MERCY - must have valid click event!
     */
    handleClick(event) {
        // NO MERCY validation
        if (!event) {
            throw new Error('Click event is required');
        }
        if (!event.target) {
            throw new Error('Click event missing target');
        }
        if (typeof event.clientX !== 'number' || typeof event.clientY !== 'number') {
            throw new Error('Click event missing coordinates');
        }

        // Extract click info
        const clickInfo = {
            coordinates: { x: event.clientX, y: event.clientY }
        };

        // Log click details
        console.log('Click handler:', {
            target: event.target,
            targetClasses: event.target?.classList,
            ...clickInfo
        });

        // NO MERCY - validate context if it exists
        if (event.context && !(event.context instanceof StateContext)) {
            throw new Error('Invalid context: must be StateContext instance');
        }

        // Check click target type
        if (event.target?.classList?.contains('note-content')) {
            return this.handleNoteContentClick(event);  // Let handleNoteContentClick handle click info
        }
        if (event.target?.classList?.contains('search-input')) {
            return {
                ...this.handleSearchClick(event),
                clickInfo,
                context: event.context  // Preserve context
            };
        }
        if (event.target?.classList?.contains('add-note')) {
            return {
                ...this.handleAddNoteClick(event),
                clickInfo,
                context: event.context  // Preserve context
            };
        }
        if (event.target?.classList?.contains('menu-button')) {
            return {
                ...this.handleMenuClick(event),
                clickInfo,
                context: event.context  // Preserve context
            };
        }
        if (event.target?.classList?.contains('trash-can')) {
            return {
                ...this.handleTrashCanClick(event),
                clickInfo,
                context: event.context  // Preserve context
            };
        }
        if (event.target?.classList?.contains('interactive')) {
            return { 
                type: 'NO_OP',
                clickInfo,
                context: event.context  // Preserve context
            };
        }

        // Check if click is inside a note
        const noteElement = DOMUtils.findNoteElement(event.target);
        if (noteElement) {
            return {
                type: 'NO_OP',
                clickInfo,
                context: event.context  // Preserve context
            };
        }

        // Non-interactive click outside any note
        return {
            type: 'CLICKED_OUTSIDE_NOTE',
            clickInfo,
            context: event.context  // Preserve context
        };
    },

    /**
     * Handle clicks on note content
     * NO MERCY - must have valid click event!
     */
    handleNoteContentClick(event) {
        // NO MERCY - validate event
        if (!event) {
            throw new Error('Note content click missing event');
        }
        if (!event.target) {
            throw new Error('Note content click event missing target');
        }
        if (typeof event.clientX !== 'number' || typeof event.clientY !== 'number') {
            throw new Error('Click event missing coordinates');
        }

        // Get note element and ID
        const noteElement = DOMUtils.findNoteElement(event.target);
        if (!noteElement) {
            throw new Error('Click not in note');
        }
        const noteId = DOMUtils.getNoteId(noteElement);
        if (!noteId) {
            throw new Error('Note missing ID');
        }

        console.log('🎯 Note content click:', {
            target: event.target,
            classList: event.target?.classList?.toString(),
            nodeType: event.target?.nodeType,
            nodeName: event.target?.nodeName,
            textContent: event.target?.textContent?.slice(0, 20), // First 20 chars
            coordinates: { x: event.clientX, y: event.clientY },
            noteId
        });

        // Get or create context
        let context = event.context;
        if (!context) {
            context = StateContext.fromStateData({
                noteId,
                cursorOffset: 0
            });
        }

        // Update context with coordinates
        context.setCoordinates({ x: event.clientX, y: event.clientY });

        return {
            type: 'NOTE_CONTENT_CLICKED',
            context
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
    handleAddNoteClick(event) {
        return {
            type: 'ADD_BUTTON_CLICKED',
            event
        };
    },

    /**
     * Handle clicks on menu button
     */
    handleMenuClick(event) {
        alert('TODO: Implement menu handling');
        return { type: 'NO_OP', event }; // TODO: Implement menu handling
    },

    /**
     * Handle clicks on trash can
     */
    handleTrashCanClick(event) {
        alert('TODO: Implement trash can handling');
        return { type: 'NO_OP', event }; // TODO: Implement trash can handling
    },

    handleKeyDown(event) {
        return {
            type: 'KEY_DOWN',
            key: event.key,
            metaKey: event.metaKey || event.ctrlKey,
            shiftKey: event.shiftKey
        };
    },

    handleDragStart(event) {
        const noteElement = DOMUtils.findNoteElement(event.target);
        if (!noteElement) {
            return { type: 'NO_OP' };
        }

        const noteId = DOMUtils.getNoteId(noteElement);
        if (!noteId) {
            throw new Error('Note element missing ID');
        }

        return {
            type: 'NOTE_DRAG_STARTED',
            noteId,
            // Only pass necessary drag data, not the whole event
            dragData: {
                clientX: event.clientX,
                clientY: event.clientY
            }
        };
    },

    handleInput(event) {
        if (DOMUtils.isNoteContent(event.target)) {
            const noteElement = DOMUtils.findNoteElement(event.target);
            if (!noteElement) {
                throw new Error('Could not find parent note element');
            }

            const noteId = DOMUtils.getNoteId(noteElement);
            if (!noteId) {
                throw new Error('Note element missing ID');
            }

            const content = DOMUtils.getNoteContentText(event.target);

            return {
                type: 'NOTE_CONTENT_CHANGED',
                noteId,
                content
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
        // If we blurred to a note, get its ID
        const noteElement = event.relatedTarget ? DOMUtils.findNoteElement(event.relatedTarget) : null;
        const noteId = noteElement ? DOMUtils.getNoteId(noteElement) : null;
        
        return {
            type: 'SEARCH_BLURRED',
            noteId  // Will be null if not clicked on note
        };
    },

    handleClickOutsideNote(event) {
        return {
            type: 'CLICKED_OUTSIDE_NOTE',
            event
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
            'Click': (e) => this.handleClick(e),
            'KeyDown': (e) => this.handleKeyDown(e),
            'DragStart': (e) => this.handleDragStart(e),
            'Input': (e) => this.handleInput(e),
            'SearchInput': (e) => this.handleSearchInput(e),
            'SearchBlur': (e) => this.handleSearchBlur(e),
            'SearchFocus': (e) => this.handleSearchClick(e),
            'ClickOutsideNote': (e) => this.handleClickOutsideNote(e),
            'FragmentLoaded': (e) => this.handleFragmentLoaded(e)
        };

        const handler = handlerMap[eventName];
        if (!handler) {
            throw new Error(`No handler for event: ${eventName}`);
        }

        return handler(event);
    }
}; 