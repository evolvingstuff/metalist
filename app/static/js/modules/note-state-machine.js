import { CONFIG } from './config.js';
import { DOMUtils } from './dom-utils.js';
import { NoteState } from './note-state.js';

/**
 * IMPORTANT ASSUMPTIONS AND GOTCHAS:
 * 
 * 1. State Transitions:
 *    - Valid transitions are strictly defined in this.transitions
 *    - Each state has enter/exit handlers to manage setup and cleanup
 *    - Enter handlers receive the fromState to make context-aware decisions
 *    - Exit handlers receive the toState to prepare for the next state
 *    - All state changes must go through proper transitions
 * 
 * 2. State Data:
 *    - Data is passed during transitions and available to handlers
 *    - currentNote and lastSavedContent are managed in editing state
 *    - searchQuery persists across transitions as app context
 *    - State data cleanup only for truly temporary state
 * 
 * 3. Async Operations:
 *    - Enter/exit handlers are async and must complete before state changes
 *    - Content saves happen in editing state's exit handler
 *    - Transitions wait for handlers to complete
 * 
 * 4. Focus Management:
 *    - Focus is managed by state enter handlers
 *    - Direct user interactions (clicks) preserve cursor position
 *    - Programmatic transitions may force focus as needed
 *    - Search ↔ Edit transitions preserve user interaction context
 * 
 * 5. Context Preservation:
 *    - Search query represents persistent app context
 *    - State exits should not clear persistent context
 *    - Only clear temporary state in exit handlers
 *    - Context survives across state transitions
 */

/**
 * State machine for managing note editing and searching states
 */
export const NoteStateMachine = {
    state: 'idle',
    data: {
        currentNote: null,
        lastSavedContent: null,
        cursorPosition: 'end'
    },
    listeners: [],

    states: {
        IDLE: 'idle',
        EDITING: 'editing',
        SEARCHING: 'searching'
    },

    transitions: {
        idle: ['editing', 'searching'],
        editing: ['idle', 'searching', 'editing'],
        searching: ['idle', 'editing']
    },

    // State handlers
    stateHandlers: {
        editing: {
            enter: async (fromState) => {
                console.log('🟢 ENTER editing state:', { from: fromState });

                // Get clicked note from event target
                const clickedContent = document.activeElement;
                const noteElement = clickedContent?.closest('.note');
                if (!noteElement) return;

                // Set up state
                NoteStateMachine.data.currentNote = noteElement;
                NoteStateMachine.data.lastSavedContent = DOMUtils.getNoteContentText(noteElement);
                
                // Set up note for editing
                DOMUtils.setNoteEditable(noteElement, true);
                DOMUtils.focusNote(noteElement);
            },
            exit: async (toState) => {
                const noteElement = NoteStateMachine.data.currentNote;
                if (!noteElement) return;

                const currentContent = DOMUtils.getNoteContentText(noteElement);
                console.log('📝 Exit editing:', {
                    content: currentContent,
                    lastSaved: NoteStateMachine.data.lastSavedContent,
                    needsSave: currentContent !== NoteStateMachine.data.lastSavedContent
                });

                // Save any pending changes
                if (NoteStateMachine.data.lastSavedContent !== currentContent) {
                    await NoteState.saveCurrentNoteWithStateMachine();
                    NoteStateMachine.data.lastSavedContent = currentContent;
                }
                
                DOMUtils.setNoteEditable(noteElement, false);
            }
        },
        searching: {
            enter: async (data, fromState) => {
                console.log('🔍 ENTER search state:', {
                    from: fromState,
                    query: data.searchQuery
                });

                console.log('Entering search state from:', fromState);
                const searchInput = document.getElementById('search-input');
                if (!searchInput) return;
                
                // Set up search and preserve existing query
                if (data.searchQuery) {
                    searchInput.value = data.searchQuery;
                }
                searchInput.focus();
            },
            exit: async (data, toState) => {
                console.log('🔍 EXIT search state:', {
                    to: toState,
                    query: data.searchQuery
                });

                console.log('Exiting search state to:', toState);
                // Search query is preserved as app context
                // No cleanup needed - query persists across transitions
            }
        },
        idle: {
            enter: async (data, fromState) => {
                console.log('⚪ ENTER idle state:', { from: fromState });
                console.log('Entering idle state from:', fromState);
            },
            exit: async (data, toState) => {
                console.log('⚪ EXIT idle state:', { to: toState });
                console.log('Exiting idle state to:', toState);
            }
        }
    },

    async transition(toState) {
        console.log('🔄 TRANSITION:', {
            from: this.state,
            to: toState
        });

        if (!this.transitions[this.state]?.includes(toState)) {
            console.error(`Invalid transition: ${this.state} → ${toState}`);
            return false;
        }

        const fromState = this.state;
        try {
            if (this.stateHandlers[fromState]?.exit) {
                await this.stateHandlers[fromState].exit(toState);
            }

            this.state = toState;

            if (this.stateHandlers[toState]?.enter) {
                await this.stateHandlers[toState].enter(fromState);
            }

            this.listeners.forEach(listener => listener(fromState, toState));
            return true;
        } catch (error) {
            console.error('State transition failed:', error);
            return false;
        }
    },

    init() {
        this.state = this.states.IDLE;
        this.data = {};
    },

    getState() {
        return {
            state: this.state,
            data: this.data
        };
    },

    addListener(callback) {
        this.listeners.push(callback);
    },

    removeListener(callback) {
        this.listeners = this.listeners.filter(l => l !== callback);
    }
}; 