import { setupKeyboardShortcuts } from './shortcuts.js';

document.addEventListener('DOMContentLoaded', () => {
    let currentEditingNote = null;
    let initialContent = null;
    let lastSavedContent = null;
    let draggedNoteId = null;

    // Set initial state of all notes to non-editable
    document.querySelectorAll('.note-content').forEach(content => {
        content.contentEditable = 'false';
    });

    async function saveNoteContent(noteElement, content) {
        const noteId = noteElement.closest('.note').dataset.id;
        console.log('Saving note:', noteId, content);
        
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
                console.log('Save successful');
            }
        } catch (error) {
            console.error('Error saving note:', error);
        }
    }

    function makeNoteEditable(noteElement) {
        const contentDiv = noteElement.querySelector('.note-content');
        
        // If switching notes, save the current one first
        if (currentEditingNote && currentEditingNote !== noteElement) {
            const currentContent = currentEditingNote.querySelector('.note-content').textContent;
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
        initialContent = contentDiv.textContent;
        lastSavedContent = initialContent;
        console.log('Started editing note, initial content:', initialContent);
    }

    // Handle clicking on notes
    document.addEventListener('click', (e) => {
        const noteElement = e.target.closest('.note');
        
        // If clicking inside a note's content
        if (noteElement && e.target.classList.contains('note-content')) {
            makeNoteEditable(noteElement);
        } 
        // If clicking outside any note
        else if (!noteElement && currentEditingNote) {
            const contentDiv = currentEditingNote.querySelector('.note-content');
            const finalContent = contentDiv.textContent;
            
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

    // Drag and Drop functionality
    document.querySelectorAll('.drag-handle').forEach(handle => {
        handle.addEventListener('dragstart', (e) => {
            const noteElement = e.target.closest('.note');
            draggedNoteId = noteElement.dataset.id;
            noteElement.classList.add('dragging');
            e.dataTransfer.setData('text/plain', '');
        });

        handle.addEventListener('dragend', (e) => {
            const noteElement = e.target.closest('.note');
            if (noteElement) {
                noteElement.classList.remove('dragging');
            }
            draggedNoteId = null;
        });
    });

    document.querySelectorAll('.note').forEach(note => {
        note.addEventListener('dragover', (e) => {
            e.preventDefault();
            if (!draggedNoteId) return;
            const note = e.target.closest('.note');
            if (!note || note.dataset.id === draggedNoteId) return;
            note.classList.add('drag-over');
        });

        note.addEventListener('dragleave', (e) => {
            const note = e.target.closest('.note');
            if (note) {
                note.classList.remove('drag-over');
            }
        });

        note.addEventListener('drop', async (e) => {
            e.preventDefault();
            const targetNote = e.target.closest('.note');
            if (!draggedNoteId || !targetNote || targetNote.dataset.id === draggedNoteId) {
                return;
            }

            // Get the bounding rectangles of both elements
            const draggedNote = document.querySelector(`.note[data-id="${draggedNoteId}"]`);
            const draggedRect = draggedNote.getBoundingClientRect();
            const targetRect = targetNote.getBoundingClientRect();

            // If the dragged note's center is above the target's center, insert before
            const isDraggingUpward = draggedRect.top > targetRect.top;
            
            // alert(`Dragging ${isDraggingUpward ? 'upward' : 'downward'}\n` +
            //       `Moving: ${draggedNoteId}\n` +
            //       `${isDraggingUpward ? 'Before' : 'After'}: ${targetNote.dataset.id}`);

            try {
                const response = await fetch(`/api/notes/${draggedNoteId}/move`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        target_id: targetNote.dataset.id,
                        insert_before: isDraggingUpward
                    })
                });

                if (response.ok) {
                    window.location.reload();
                } else {
                    alert('Move failed: ' + await response.text());
                }
            } catch (error) {
                alert('Error moving note: ' + error);
            }
        });
    });

    // Polling for changes while editing
    setInterval(() => {
        if (currentEditingNote) {
            const currentContent = currentEditingNote.querySelector('.note-content').textContent;
            if (currentContent !== lastSavedContent) {
                console.log('Poll detected change, saving');
                saveNoteContent(currentEditingNote, currentContent);
            }
        }
    }, 2000);

    document.getElementById('add-note-btn').addEventListener('click', async () => {
        const response = await fetch('/api/notes/new', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ content: '' })
        });
        
        if (response.ok) {
            window.location.reload();
        }
    });

    function stopEditing() {
        if (currentEditingNote) {
            const contentDiv = currentEditingNote.querySelector('.note-content');
            const finalContent = contentDiv.textContent;
            
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

    // Setup keyboard shortcuts
    setupKeyboardShortcuts({
        stopEditing
    });
}); 