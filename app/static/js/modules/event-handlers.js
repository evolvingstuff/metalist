import { CONFIG } from './config.js';
import { NotesAPI } from './api-client.js';
import { DOMUtils } from './dom-utils.js';
import { NoteState } from './note-state.js';
import { setupKeyboardShortcuts } from '../shortcuts.js';
import { NoteStateMachine } from './note-state-machine.js';

/**
 * IMPORTANT ASSUMPTIONS AND GOTCHAS:
 * 
 * 1. Event Order:
 *    - Events might fire during state transitions
 *    - Click and blur events must coordinate for proper state changes
 *    - Focus management depends on event order
 * 
 * 2. State Machine Interaction:
 *    - Events trigger state transitions via NoteState
 *    - Direct state machine calls only for idle transitions
 *    - Search blur handler manages search → editing transition
 * 
 * 3. Cursor Position:
 *    - Click events preserve natural cursor position
 *    - Programmatic focus may override cursor position
 *    - Search → Edit transition must preserve click position
 * 
 * 4. Event Cleanup:
 *    - State transitions might remove elements
 *    - Event listeners must check element validity
 *    - Async handlers must verify state before acting
 */

/**
 * Handles DOM events and coordinates with state machine
 */
export const EventHandlers = {
    init() {
        // Global event listeners
        document.addEventListener('click', this.handleClick.bind(this));
        document.addEventListener('input', this.handleInput.bind(this));
        document.addEventListener('blur', this.handleBlur.bind(this), true);
        document.addEventListener('paste', this.handlePaste.bind(this));
        document.addEventListener('keydown', this.handleKeyDown.bind(this));

        this.initSearchHandlers();
    },

    /**
     * Handle click events
     */
    handleClick(event) {
        console.log('👆 CLICK EVENT:', {
            target: {
                element: event.target?.className,
                isNoteContent: DOMUtils.isNoteContent(event.target)
            },
            currentState: NoteStateMachine.state,
            activeElement: document.activeElement?.className,
            stack: new Error().stack
        });

        const noteElement = DOMUtils.findNoteElement(event.target);
        if (noteElement && DOMUtils.isNoteContent(event.target)) {
            console.log('🖱 Note state:', {
                pristine: {
                    classList: [...event.target.classList],
                    contentEditable: event.target.contentEditable,
                    attributes: [...event.target.attributes].map(a => `${a.name}="${a.value}"`),
                },
                parent: {
                    classList: [...noteElement.classList],
                    attributes: [...noteElement.attributes].map(a => `${a.name}="${a.value}"`)
                }
            });
            
            // If we're in search mode, let the blur handler handle it
            if (NoteStateMachine.state === 'searching') {
                return;
            }
            
            // Direct transition if already editing
            if (NoteStateMachine.state === 'editing') {
                console.log('   ➡️ Direct edit→edit transition');
                NoteStateMachine.transition('editing', {
                    currentNote: noteElement,
                    lastSavedContent: DOMUtils.getNoteContentText(noteElement)
                });
                return;
            }
            
            console.log('   ⚪ Going through NoteState.startEditing');
            NoteState.startEditing(noteElement);
        }
    },

    /**
     * Handle input events
     */
    handleInput(event) {
        if (DOMUtils.isNoteContent(event.target)) {
            NoteState.handleContentChange();
        }
    },

    /**
     * Handle blur events
     */
    handleBlur(event) {
        // Only handle blur for note content
        if (!DOMUtils.isNoteContent(event.target)) {
            console.log('🌟 Blur: Ignoring - not note content');
            return;
        }

        const noteElement = DOMUtils.findNoteElement(event.target);
        if (!noteElement) {
            console.log('🌟 Blur: Ignoring - no note element');
            return;
        }

        // If clicking within any note content or search, don't exit edit mode
        if ((event.relatedTarget && DOMUtils.isNoteContent(event.relatedTarget)) || 
            event.relatedTarget?.id === 'search-input') {
            console.log('🌟 Blur: Preserving edit mode - clicking note content or search');
            return;
        }

        console.log('🌟 Blur: Transitioning to idle', {
            from: event.target?.className,
            to: event.relatedTarget?.className,
            currentState: NoteStateMachine.state
        });
        
        // Only transition to idle if we're not clicking another note's content
        NoteStateMachine.transition('idle');
    },

    /**
     * Initialize search handlers
     */
    initSearchHandlers() {
        const searchInput = document.getElementById('search-input');
        if (!searchInput) return;

        // Enter search mode on focus
        searchInput.addEventListener('focus', async () => {
            const query = searchInput.value;
            await NoteState.startSearch(query);
        });

        // Handle search input
        searchInput.addEventListener('input', async (event) => {
            const query = event.target.value;
            await NoteState.startSearch(query);
        });

        // Handle blur from search - use capture phase
        searchInput.addEventListener('blur', async (event) => {
            console.log('🔍 BLUR EVENT:', {
                relatedTarget: event.relatedTarget?.className,
                activeElement: document.activeElement?.className,
                currentState: NoteStateMachine.state
            });
            // If clicking a note, transition directly to editing
            if (event.relatedTarget?.closest('.note')) {
                event.stopImmediatePropagation();  // Stop ALL other handlers
                event.preventDefault();
                
                const noteElement = event.relatedTarget.closest('.note');
                // Direct transition from search → edit
                await NoteStateMachine.transition('editing', {
                    currentNote: noteElement,
                    lastSavedContent: DOMUtils.getNoteContentText(noteElement)
                });
                return;
            }
            // Only go to idle if not clicking a note
            NoteStateMachine.transition('idle');
        }, true);  // true = use capture phase

        // Global click handler
        document.addEventListener('click', (event) => {
            console.log('🖱️ CLICK EVENT:', {
                target: event.target?.className,
                activeElement: document.activeElement?.className,
                currentState: NoteStateMachine.state
            });
        }, true);
    },

    /**
     * Handle keyboard shortcuts
     */
    handleKeyDown(event) {
        // Command/Control key shortcuts
        if (event.metaKey || event.ctrlKey) {
            switch (event.key) {
                case 'f':
                    event.preventDefault();
                    NoteState.startSearch();
                    break;
                    
                case 'Enter':
                    event.preventDefault();
                    // Handle save explicitly if needed
                    break;
            }
        }
    },

    /**
     * Handle paste events
     */
    async handlePaste(event) {
        const noteElement = DOMUtils.findNoteElement(event.target);
        if (!noteElement || !DOMUtils.isNoteContent(event.target)) return;

        const items = (event.clipboardData || event.originalEvent.clipboardData).items;
        for (const item of items) {
            if (item.type.indexOf('image') === 0) {
                event.preventDefault();
                await this.handleImagePaste(item, noteElement);
            }
        }
    },

    /**
     * Handle image paste
     */
    async handleImagePaste(item, noteElement) {
        const blob = item.getAsFile();
        const reader = new FileReader();
        
        reader.onload = async (event) => {
            const img = document.createElement('img');
            img.src = event.target.result;
            img.style.maxWidth = '100%';
            
            const selection = window.getSelection();
            const range = selection.getRangeAt(0);
            range.deleteContents();
            range.insertNode(img);
            
            await NoteState.saveCurrentNote();
        };
        
        reader.readAsDataURL(blob);
    }
}; 