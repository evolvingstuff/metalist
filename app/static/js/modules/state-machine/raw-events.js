import { DOMUtils } from '../dom-utils.js';
import { StateContext } from './state-context.js';
import { StateMachine } from './state-machine-controller.js'; 

export const RawEvents = {

    handleClick(domEvent) {
                                
        if (!domEvent) {
            throw new Error('Click missing event');
        }
        if (!domEvent.target) {
            throw new Error('Click event missing target');
        }

        const clickInfo = {
            x: domEvent.clientX,
            y: domEvent.clientY
        };

        if (DOMUtils.isNoteContent(domEvent.target)) {
            return this.handleNoteContentClick(domEvent);  
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

        const noteElement = DOMUtils.findNoteElement(domEvent.target);
        if (noteElement) {
            return this.handleNoteClick(domEvent);
        }

        return this.handleClickOutsideNote(domEvent);
    },

    handleNoteContentClick(domEvent) {
        if (!domEvent) {
            throw new Error('Note content click missing event');
        }
        if (!domEvent.target) {
            throw new Error('Note content click event missing target');
        }
        if (typeof domEvent.clientX !== 'number' || typeof domEvent.clientY !== 'number') {
            throw new Error('Click event missing coordinates');
        }

        StateMachine.resetOnNewEvent();

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
            textContent: domEvent.target?.textContent?.slice(0, 20), 
            coordinates: { x: domEvent.clientX, y: domEvent.clientY },
            noteId
        });

        const content = DOMUtils.getNoteContentHTMLById(noteId);
        const cursorOffset = DOMUtils.getCursorOffsetFromClick(noteElement, { x: domEvent.clientX, y: domEvent.clientY });
                                
        StateMachine.currentStateContext
            .setType('NOTE_CONTENT_CLICKED')
            .setTargetNoteId(noteId)  
            .setCoordinates({ x: domEvent.clientX, y: domEvent.clientY })
            .setCursorOffset(cursorOffset);  
    },

    handleSearchClick(domEvent) {
        if (!domEvent) {
            throw new Error('Search click missing event');
        }
        if (!domEvent.target) {
            throw new Error('Search click missing target');
        }

        StateMachine.resetOnNewEvent();
                                
        StateMachine.currentStateContext
            .setType('SEARCH_CLICKED');
    },

    handleAddNoteClick(domEvent) {
        StateMachine.currentStateContext
            .setType('ADD_BUTTON_CLICKED')
            .setShiftKey(domEvent.shiftKey);
    },

    handleMenuClick(domEvent) {
        StateMachine.resetOnNewEvent();
                                
        StateMachine.currentStateContext
            .setType('MENU_CLICKED');
    },

    handleTrashCanClick(domEvent) {
        StateMachine.resetOnNewEvent();
                                
        StateMachine.currentStateContext
            .setType('TRASH_CAN_CLICKED');
    },

    handleKeyDown(domEvent) {
        if (!domEvent) {
            throw new Error('Key down missing event');
        }

        StateMachine.resetOnNewEvent();

        return StateMachine.currentStateContext
            .setType('KEY_DOWN')
            .setKey(domEvent.key)
            .setMetaKey(domEvent.metaKey || domEvent.ctrlKey)
            .setShiftKey(domEvent.shiftKey);
    },

    handleDragStart(domEvent) {
                                
        if (!domEvent) {
            throw new Error('Drag start missing event');
        }
        if (!domEvent.target) {
            throw new Error('Drag start event missing target');
        }

        StateMachine.resetOnNewEvent();

        const noteElement = DOMUtils.findNoteElement(domEvent.target);
        if (!noteElement) {
            throw new Error('Drag start not in note');
        }

        const noteId = DOMUtils.getNoteId(noteElement);
        if (!noteId) {
            throw new Error('Note missing ID');
        }

        StateMachine.currentStateContext
            .setType('DRAG_STARTED')
            .setNoteId(noteId);
    },

    handleInput(domEvent) {
        if (!domEvent) {
            throw new Error('Input missing event');
        }

        StateMachine.currentStateContext
            .setType('NOTE_CONTENT_CHANGED');
    },

    handleSearchInput(domEvent) {
        if (!domEvent) {
            throw new Error('Search input missing event');
        }

        StateMachine.resetOnNewEvent();

        StateMachine.currentStateContext
            .setType('SEARCH_QUERY_CHANGED')
            .setQuery(domEvent.target.value);
    },

    handleSearchBlur(domEvent) {
        if (!domEvent) {
            throw new Error('Search blur missing event');
        }

        StateMachine.resetOnNewEvent();

        const noteElement = domEvent.relatedTarget ? DOMUtils.findNoteElement(domEvent.relatedTarget) : null;
        const noteId = noteElement ? DOMUtils.getNoteId(noteElement) : null;
                                
        StateMachine.currentStateContext
            .setType('SEARCH_BLURRED')
            .setNoteId(noteId);  
    },

    handleClickOutsideNote(domEvent) {
        if (!domEvent) {
            throw new Error('Click outside note missing event');
        }

        StateMachine.resetOnNewEvent();

        StateMachine.currentStateContext
            .setType('CLICKED_OUTSIDE_NOTE')
            .setCoordinates({ x: domEvent.clientX, y: domEvent.clientY });
    },

    handleFragmentLoaded(domEvent) {
        if (!domEvent) {
            throw new Error('Fragment loaded missing event');
        }

        StateMachine.resetOnNewEvent();

        StateMachine.currentStateContext
            .setType('FRAGMENT_LOADED');
    },

    handleInteractiveClick(domEvent) {
        if (!domEvent) {
            throw new Error('Interactive click missing event');
        }

        StateMachine.resetOnNewEvent();

        StateMachine.currentStateContext
            .setType('NO_OP')
            .setCoordinates({ x: domEvent.clientX, y: domEvent.clientY });
    },

    handleNoteClick(domEvent) {
        if (!domEvent) {
            throw new Error('Note click missing event');
        }

        StateMachine.resetOnNewEvent();

        StateMachine.currentStateContext
            .setType('NO_OP')
            .setCoordinates({ x: domEvent.clientX, y: domEvent.clientY });
    }
}; 