import { setupKeyboardShortcuts } from './shortcuts.js';

// Move variables to global scope
let currentEditingNote = null;
let initialContent = null;
let lastSavedContent = null;
let draggedNoteId = null;
let dragTarget = null;

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

    // Handle drag and drop
    document.addEventListener('dragstart', (e) => {
        const noteElement = e.target.closest('.note');
        if (noteElement) {
            draggedNoteId = noteElement.dataset.id;
            noteElement.classList.add('dragging');
        }
    });

    document.addEventListener('dragend', (e) => {
        const noteElement = e.target.closest('.note');
        if (noteElement) {
            noteElement.classList.remove('dragging');
            if (dragTarget) {
                dragTarget.classList.remove('drag-over');
                dragTarget.classList.remove('drag-before');
                dragTarget.classList.remove('drag-after');
                dragTarget.classList.remove('drag-inside');
            }
        }
    });

    document.addEventListener('dragover', (e) => {
        e.preventDefault();
        const noteElement = e.target.closest('.note');
        
        // Always remove existing highlights first
        if (dragTarget) {
            dragTarget.classList.remove('drag-over');
            dragTarget.classList.remove('drag-before');
            dragTarget.classList.remove('drag-after');
            dragTarget.classList.remove('drag-inside');
        }
        
        if (noteElement && noteElement.dataset.id !== draggedNoteId) {
            // Get dimensions for position detection
            const rect = noteElement.getBoundingClientRect();
            const edgeSize = rect.width * 0.25; // 25% from left edge for nesting
            const midPoint = rect.top + rect.height / 2;
            
            // Determine drop type based on position
            let dropType;
            if (e.clientX < rect.left + edgeSize) {
                // Near the left edge - insert as sibling
                dropType = e.clientY < midPoint ? 'before' : 'after';
            } else {
                // Away from left edge - insert as child
                dropType = 'inside';
            }
            
            // Check if move would be meaningful
            const draggedElement = document.querySelector(`[data-id="${draggedNoteId}"]`);
            const wouldMove = isMoveMeaningful(draggedElement, noteElement, dropType);
            
            if (wouldMove) {
                dragTarget = noteElement;
                dragTarget.classList.add('drag-over');
                if (dropType === 'before') {
                    dragTarget.classList.add('drag-before');
                } else if (dropType === 'after') {
                    dragTarget.classList.add('drag-after');
                } else {
                    dragTarget.classList.add('drag-inside');
                }
            } else {
                dragTarget = null;
            }
        } else {
            dragTarget = null;
        }
    });

    document.addEventListener('drop', async (e) => {
        e.preventDefault();
        if (draggedNoteId && dragTarget) {
            const targetId = dragTarget.dataset.id;
            const dropType = dragTarget.classList.contains('drag-before') ? 'before' :
                           dragTarget.classList.contains('drag-after') ? 'after' : 'inside';
            
            await moveNote(draggedNoteId, targetId, dropType);
        }
        
        // Clean up
        if (dragTarget) {
            dragTarget.classList.remove('drag-over');
            dragTarget.classList.remove('drag-before');
            dragTarget.classList.remove('drag-after');
            dragTarget.classList.remove('drag-inside');
        }
        dragTarget = null;
        draggedNoteId = null;
    });

    // Add new note button handler
    document.getElementById('add-note-btn').addEventListener('click', async () => {
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

    console.log('Sending move request with params:', params);  // Debug log

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