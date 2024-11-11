document.addEventListener('DOMContentLoaded', () => {
    let currentEditingNote = null;

    // Set initial state of all notes to non-editable
    document.querySelectorAll('.note-content').forEach(content => {
        content.contentEditable = 'false';
    });

    // Function to make a note editable
    function makeNoteEditable(noteElement) {
        console.log('Making note editable:', noteElement); // Debug log
        
        // If there's already a note being edited, make it non-editable
        if (currentEditingNote && currentEditingNote !== noteElement) {
            currentEditingNote.querySelector('.note-content').contentEditable = 'false';
            currentEditingNote.classList.remove('editing');
        }

        // Make the clicked note editable
        const contentDiv = noteElement.querySelector('.note-content');
        contentDiv.contentEditable = 'true';
        noteElement.classList.add('editing');
        contentDiv.focus();
        currentEditingNote = noteElement;
    }

    // Handle clicking on notes
    document.addEventListener('click', (e) => {
        const noteElement = e.target.closest('.note');
        console.log('Click event:', e.target, noteElement); // Debug log
        
        // If clicking inside a note's content
        if (noteElement && e.target.classList.contains('note-content')) {
            makeNoteEditable(noteElement);
        } 
        // If clicking outside any note
        else if (!noteElement && currentEditingNote) {
            currentEditingNote.querySelector('.note-content').contentEditable = 'false';
            currentEditingNote.classList.remove('editing');
            currentEditingNote = null;
        }
    });

    // Add note button handler
    document.getElementById('add-note-btn').addEventListener('click', async () => {
        const response = await fetch('/api/notes/new', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ content: '' })
        });
        
        if (response.ok) {
            window.location.reload();  // Refresh to show new note
        }
    });
}); 