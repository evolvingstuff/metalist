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
    data: {},
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
            enter: async (data, fromState) => {
                console.log('🟢 ENTER editing state:', {
                    from: fromState,
                    noteElement: data.currentNote,
                    activeElement: document.activeElement?.className
                });

                console.log('Entering editing state from:', fromState);
                const noteElement = data.currentNote;
                
                // Set up note for editing
                DOMUtils.setNoteEditable(noteElement, true);
                
                // Only force focus if coming from idle state
                if (fromState === 'idle' && !document.activeElement?.closest('.note-content')) {
                    console.log('   👆 Forcing focus because coming from idle');
                    DOMUtils.focusNote(noteElement);
                } else {
                    console.log('   🖱️ Preserving natural focus/cursor');
                }
            },
            exit: async (data, toState) => {
                console.log('🔴 EXIT editing state:', {
                    to: toState,
                    noteElement: data.currentNote
                });

                console.log('Exiting editing state to:', toState);
                const noteElement = data.currentNote;
                if (!noteElement) return;

                // Save any pending changes
                if (data.lastSavedContent !== DOMUtils.getNoteContentText(noteElement)) {
                    console.log('   💾 Saving changes before exit');
                    await NoteState.saveCurrentNoteWithStateMachine();
                }
                
                // Make note non-editable
                DOMUtils.setNoteEditable(noteElement, false);

                // Remove the selection to hide the blinking cursor without triggering blur events
                const selection = window.getSelection();
                if (selection) {
                    selection.removeAllRanges();
                }
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

    async transition(toState, data = {}) {
        console.log('🔄 TRANSITION:', {
            from: this.state,
            to: toState,
            data,
            stack: new Error().stack.split('\n').slice(1,3).join('\n')  // Just first 2 stack frames
        });
        console.log(`State transition: ${this.state} → ${toState}`, data);
        
        if (!this.transitions[this.state]?.includes(toState)) {
            console.warn(`Invalid transition: ${this.state} → ${toState}`);
            return false;
        }

        const fromState = this.state;
        
        try {
            // Exit current state
            if (this.stateHandlers[fromState]?.exit) {
                await this.stateHandlers[fromState].exit(this.data, toState);
            }

            // Update state
            this.state = toState;
            this.data = data;

            // Enter new state
            if (this.stateHandlers[toState]?.enter) {
                await this.stateHandlers[toState].enter(data, fromState);
            }

            // Notify listeners
            this.listeners.forEach(listener => listener(fromState, toState, data));
            
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