import { setupKeyboardShortcuts } from './shortcuts.js';

// Move variables to global scope
let currentEditingNote = null;
let initialContent = null;
let lastSavedContent = null;
let draggedNoteId = null;
let dragTarget = null;
let isDraggingAddButton = false;

// Add Position enum to match backend
const Position = {
    BEFORE: 'BEFORE',
    AFTER: 'AFTER'
};



async function handleImagePaste(e, noteElement) {
    const items = (e.clipboardData || e.originalEvent.clipboardData).items;
    
    for (const item of items) {
        if (item.type.indexOf('image') === 0) {
            e.preventDefault();
            
            const blob = item.getAsFile();
            const reader = new FileReader();
            
            reader.onload = async function(event) {
                const img = document.createElement('img');
                img.src = event.target.result;
                img.style.maxWidth = '100%';
                
                const selection = window.getSelection();
                const range = selection.getRangeAt(0);
                range.deleteContents();
                range.insertNode(img);
                
                const contentDiv = noteElement.querySelector('.note-content');
                await saveNoteContent(noteElement, contentDiv.innerHTML);
            };
            
            reader.readAsDataURL(blob);
        }
    }
}

document.addEventListener('DOMContentLoaded', () => {
    // Set initial state of all notes to non-editable
    document.querySelectorAll('.note-content').forEach(content => {
        content.contentEditable = 'false';
    });

    // Handle clicking on notes
    document.addEventListener('click', (e) => {
        const noteElement = e.target.closest('.note');
        
        if (noteElement && e.target.closest('.note-content')) {
            makeNoteEditable(noteElement);
        } 
        else if (!noteElement && currentEditingNote) {
            const contentDiv = currentEditingNote.querySelector('.note-content');
            const finalContent = contentDiv.innerHTML;
            
            if (finalContent !== lastSavedContent) {
                console.log('Saving note before exit');
                saveNoteContent(currentEditingNote, finalContent);
            }
            
            contentDiv.contentEditable = 'false';
            currentEditingNote.classList.remove('editing');
            currentEditingNote = null;
            initialContent = null;
            lastSavedContent = null;
        }
    });

    // Add new note button handler with drag check
    const addButton = document.querySelector('.add-note');
    if (addButton) {
        // Check if there are any existing notes
        const hasNotes = document.querySelector('.note') !== null;
        
        // Only allow dragging if there are notes
        addButton.draggable = hasNotes;
        
        addButton.addEventListener('click', async () => {
            const parentId = null;  // Add at root level by default
            const response = await fetch('/api/notes/new', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ parent_id: parentId })
            });
            
            if (response.ok) {
                window.location.reload();
            }
        });
    }

    // Polling for changes while editing
    setInterval(() => {
        if (currentEditingNote) {
            const currentContent = currentEditingNote.querySelector('.note-content').innerHTML;
            if (currentContent !== lastSavedContent) {
                console.log('Poll detected change, saving');
                saveNoteContent(currentEditingNote, currentContent);
            }
        }
    }, 2000);

    // Setup keyboard shortcuts
    setupKeyboardShortcuts({
        stopEditing: () => {
            if (currentEditingNote) {
                const contentDiv = currentEditingNote.querySelector('.note-content');
                const finalContent = contentDiv.innerHTML;
                
                if (finalContent !== lastSavedContent) {
                    console.log('Saving note before exit');
                    saveNoteContent(currentEditingNote, finalContent);
                }
                
                contentDiv.contentEditable = 'false';
                currentEditingNote.classList.remove('editing');
                currentEditingNote = null;
                initialContent = null;
                lastSavedContent = null;
            }
        }
    });

    // Handle paste events
    document.addEventListener('paste', (e) => {
        const noteElement = e.target.closest('.note');
        if (noteElement && e.target.classList.contains('note-content')) {
            handleImagePaste(e, noteElement);
        }
    });

    // Verify trash can exists
    const trashCan = document.getElementById('trash-can');
    if (!trashCan) {
        alert('Trash can not found!');
    }

    const state = JSON.parse(localStorage.getItem('editingState'));
    if (state) {
        const noteElement = document.querySelector(`[data-id="${state.noteId}"]`);
        if (noteElement) {
            makeNoteEditable(noteElement);
            restoreCursorPosition(noteElement, state.cursorPosition);
        }
    }

    document.querySelectorAll('.note').forEach(note => {
        note.addEventListener('mouseenter', () => {
            document.querySelectorAll('.drag-handle').forEach(handle => {
                handle.style.visibility = 'hidden';
            });
            const dragHandle = note.querySelector('.drag-handle');
            if (dragHandle) {
                dragHandle.style.visibility = 'visible';
            }
        });

        note.addEventListener('mouseleave', () => {
            const dragHandle = note.querySelector('.drag-handle');
            if (dragHandle) {
                dragHandle.style.visibility = 'hidden';
            }
        });
    });
});

async function saveNoteContent(noteElement, content) {
    const noteId = noteElement.dataset.id;
    try {
        const response = await fetch(`/api/notes/${noteId}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ content })
        });
        
        if (response.ok) {
            lastSavedContent = content;
        }
    } catch (error) {
        console.error('Error saving note:', error);
    }
}

function makeNoteEditable(noteElement) {
    const contentDiv = noteElement.querySelector('.note-content');
    
    // If switching notes, save the current one first
    if (currentEditingNote && currentEditingNote !== noteElement) {
        const currentContent = currentEditingNote.querySelector('.note-content').innerHTML;
        if (currentContent !== lastSavedContent) {
            console.log('Saving previous note before switching');
            saveNoteContent(currentEditingNote, currentContent);
        }
        currentEditingNote.querySelector('.note-content').contentEditable = 'false';
        currentEditingNote.classList.remove('editing');
    }

    contentDiv.contentEditable = 'true';
    noteElement.classList.add('editing');
    contentDiv.focus();
    currentEditingNote = noteElement;
    initialContent = contentDiv.innerHTML;
    lastSavedContent = initialContent;
    console.log('Started editing note, initial content:', initialContent);
}

function isMoveMeaningful(draggedElement, targetElement, dropType) {
    console.log('isMeaningfulMove()')
    // Don't allow a note to become its own parent
    if (dropType === 'inside' && targetElement.dataset.id === draggedElement.dataset.id) {
        return false;
    }

    // Don't allow dropping into own children
    if (dropType === 'inside' && targetElement.closest(`[data-id="${draggedElement.dataset.id}"]`)) {
        return false;
    }
    
    // If trying to insert before immediate next sibling
    if (dropType === 'before' && draggedElement.nextElementSibling === targetElement) {
        return false;
    }
    
    // If trying to insert after immediate previous sibling
    if (dropType === 'after' && draggedElement.previousElementSibling === targetElement) {
        return false;
    }
    
    // If trying to move into current parent
    if (dropType === 'inside' && targetElement.dataset.id === draggedElement.dataset.parentId) {
        return false;
    }
    
    return true;
}

async function moveNote(noteId, targetId, dropType) {
    // Convert UI drop type to API parameters
    let params;
    
    if (dropType === 'inside') {
        // Moving to become child of target
        params = {
            new_parent_id: targetId,
            sibling_id: null,
            position: null
        };
    } else {
        const targetElement = document.querySelector(`[data-id="${targetId}"]`);
        const parentId = targetElement.dataset.parentId;
        // Moving relative to a sibling - use null for root level
        params = {
            new_parent_id: parentId === "" || parentId === undefined || parentId === "None" ? null : parentId,
            sibling_id: targetId,
            position: dropType === 'before' ? Position.BEFORE : Position.AFTER
        };
    }

    console.log('Sending move request with params:', JSON.stringify(params, null, 2));  // More detailed debug log

    try {
        const response = await fetch(`/api/notes/${noteId}/move`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(params)
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to move note');
        }

        // Refresh the page to show new structure
        window.location.reload();
    } catch (error) {
        console.error('Error moving note:', error);
        alert(error.message);
    }
}

function handleAddButtonDragOver(e, noteElement) {
    console.log('Add button drag over:', noteElement.dataset.id)
    const rect = noteElement.getBoundingClientRect();
    const edgeSize = rect.width * 0.25;
    const midPoint = rect.top + rect.height / 2;
    
    dragTarget = noteElement;
    dragTarget.classList.add('drag-over');
    
    if (e.clientX < rect.left + edgeSize) {
        if (e.clientY < midPoint) {
            dragTarget.classList.add('drag-before');
        } else {
            dragTarget.classList.add('drag-after');
        }
    } else {
        dragTarget.classList.add('drag-inside');
    }
}

function handleNoteDragOver(e, noteElement) {
    console.log('Note drag over:', noteElement.dataset.id, draggedNoteId)
    if (noteElement.dataset.id === draggedNoteId) return;
    
    const rect = noteElement.getBoundingClientRect();
    const edgeSize = rect.width * 0.25;
    const midPoint = rect.top + rect.height / 2;
    
    let dropType;
    if (e.clientX < rect.left + edgeSize) {
        dropType = e.clientY < midPoint ? 'before' : 'after';
    } else {
        dropType = 'inside';
    }
    
    const draggedElement = document.querySelector(`[data-id="${draggedNoteId}"]`);
    if (draggedElement && isMoveMeaningful(draggedElement, noteElement, dropType)) {
        dragTarget = noteElement;
        dragTarget.classList.add('drag-over');
        if (dropType === 'before') {
            dragTarget.classList.add('drag-before');
        } else if (dropType === 'after') {
            dragTarget.classList.add('drag-after');
        } else {
            dragTarget.classList.add('drag-inside');
        }
    }
}

// Update our dragstart handler to use existing div
document.addEventListener('dragstart', (e) => {
    // Reset all drag state
    draggedNoteId = null;
    isDraggingAddButton = false;
    
    const addButton = e.target.closest('.add-note');
    const dragHandle = e.target.closest('.drag-handle');
    const noteElement = e.target.closest('.note');
    
    if (addButton) {
        isDraggingAddButton = true;
        // Create ghost image for drag
        const ghost = document.createElement('div');
        ghost.className = 'note';
        ghost.innerHTML = '<div class="note-content">New note</div>';
        document.body.appendChild(ghost);
        e.dataTransfer.setDragImage(ghost, 0, 0);
        setTimeout(() => document.body.removeChild(ghost), 0);
    } else if (dragHandle && noteElement) {
        draggedNoteId = noteElement.dataset.id;
        noteElement.classList.add('dragging');
    }
});

document.addEventListener('dragover', (e) => {
    e.preventDefault();
    const hoverNote = e.target.closest('.note');
    const trashCan = e.target.closest('#trash-can');
    
    // Clear existing highlights
    if (dragTarget) {
        dragTarget.classList.remove('drag-over', 'drag-before', 'drag-after', 'drag-inside');
    }
    
    const draggedElement = document.querySelector(`[data-id="${draggedNoteId}"]`);
    if (draggedElement) {
        draggedElement.classList.remove('drag-trash');
    }
    
    if (trashCan) {
        dragTarget = trashCan;
        dragTarget.classList.add('drag-over');
        
        // Add red border to the dragged note
        if (draggedElement) {
            draggedElement.classList.add('drag-trash');
        }
    } else if (hoverNote) {
        if (isDraggingAddButton) {
            handleAddButtonDragOver(e, hoverNote);
        } else if (draggedNoteId) {
            handleNoteDragOver(e, hoverNote);
        }
    } else {
        dragTarget = null;
    }
});

document.addEventListener('drop', (e) => {
    e.preventDefault();
    const trashCan = e.target.closest('#trash-can');
    const hoverNote = e.target.closest('.note');
    
    if (trashCan && draggedNoteId) {
        fetch(`/api/notes/${draggedNoteId}`, {
            method: 'DELETE'
        }).then(() => window.location.reload());
    } else if (hoverNote && dragTarget) {
        const targetId = dragTarget.dataset.id;
        const dropType = dragTarget.classList.contains('drag-before') ? 'before' :
                       dragTarget.classList.contains('drag-after') ? 'after' : 'inside';

        if (draggedNoteId) {
            moveNote(draggedNoteId, targetId, dropType);
        } else if (isDraggingAddButton) {
            // Create new note with position
            const parentId = dropType === 'inside' ? targetId : hoverNote.dataset.parentId;
            const payload = {
                new_parent_id: parentId === "None" || parentId === "" || parentId === undefined ? null : parentId,
            };
            
            // Only add sibling and position for before/after drops
            if (dropType !== 'inside') {
                payload.sibling_id = targetId;
                payload.position = dropType === 'before' ? Position.BEFORE : Position.AFTER;
            }

            fetch('/api/notes/new-drop', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(payload)
            }).then(() => window.location.reload());
        }
    }
    
    // Clean up
    if (dragTarget) {
        dragTarget.classList.remove('drag-over', 'drag-before', 'drag-after', 'drag-inside');
    }
    dragTarget = null;
    draggedNoteId = null;
    isDraggingAddButton = false;
});

document.addEventListener('dragend', (e) => {
    // Clean up any drag state
    if (dragTarget) {
        dragTarget.classList.remove('drag-over', 'drag-before', 'drag-after', 'drag-inside', 'drag-trash');
    }
    
    const noteElement = e.target.closest('.note');
    if (noteElement) {
        noteElement.classList.remove('dragging', 'drag-trash');
    }
    
    // Reset all drag state
    dragTarget = null;
    draggedNoteId = null;
    isDraggingAddButton = false;
});

document.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !isDraggingAddButton && !currentEditingNote) {
        const addButton = document.querySelector('.add-note');
        if (addButton) {
            addButton.click();
        }
    }

    if (e.key === 'Backspace' && e.metaKey && currentEditingNote) {
        const noteId = currentEditingNote.dataset.id;
        if (noteId) {
            fetch(`/api/notes/${noteId}`, {
                method: 'DELETE'
            }).then(() => window.location.reload());
        }
    }

    if (e.metaKey && currentEditingNote) {
        const noteId = currentEditingNote.dataset.id;

        const saveCursorPosition = () => {
            const selection = window.getSelection();
            if (selection.rangeCount > 0) {
                const range = selection.getRangeAt(0);
                const preCaretRange = range.cloneRange();
                preCaretRange.selectNodeContents(currentEditingNote.querySelector('.note-content'));
                preCaretRange.setEnd(range.endContainer, range.endOffset);
                const cursorPosition = preCaretRange.toString().length;
                localStorage.setItem('editingState', JSON.stringify({ noteId, cursorPosition }));
            }
        };

        if (e.key === 'ArrowUp') {
            e.preventDefault();
            const prevSibling = currentEditingNote.previousElementSibling;
            if (prevSibling) {
                saveCursorPosition();
                const siblingId = prevSibling.dataset.id;
                moveNote(noteId, siblingId, 'before').then(() => {
                    const state = JSON.parse(localStorage.getItem('editingState'));
                    const newNote = document.querySelector(`[data-id="${state.noteId}"]`);
                    makeNoteEditable(newNote);
                    restoreCursorPosition(newNote, state.cursorPosition);
                });
            }
        }

        if (e.key === 'ArrowDown') {
            e.preventDefault();
            const nextSibling = currentEditingNote.nextElementSibling;
            if (nextSibling) {
                saveCursorPosition();
                const siblingId = nextSibling.dataset.id;
                moveNote(noteId, siblingId, 'after').then(() => {
                    const state = JSON.parse(localStorage.getItem('editingState'));
                    const newNote = document.querySelector(`[data-id="${state.noteId}"]`);
                    makeNoteEditable(newNote);
                    restoreCursorPosition(newNote, state.cursorPosition);
                });
            }
        }
    }
}); 

function exitEditingMode() {
    if (currentEditingNote) {
        const contentDiv = currentEditingNote.querySelector('.note-content');
        const finalContent = contentDiv.innerHTML;
        
        if (finalContent !== lastSavedContent) {
            console.log('Saving note before exit');
            saveNoteContent(currentEditingNote, finalContent);
        }
        
        contentDiv.contentEditable = 'false';
        currentEditingNote.classList.remove('editing');
        currentEditingNote = null;
        initialContent = null;
        lastSavedContent = null;
        
        // Clear local storage
        localStorage.removeItem('editingState');
    }
} 

function restoreCursorPosition(noteElement, position) {
    const contentDiv = noteElement.querySelector('.note-content');
    const range = document.createRange();
    const selection = window.getSelection();
    range.setStart(contentDiv.firstChild, position);
    range.collapse(true);
    selection.removeAllRanges();
    selection.addRange(range);
} 