/**
 * IMPORTANT: Always use cache busting when visiting pages in tests.
 * This ensures we get fresh JS files and don't use cached versions:
 * cy.visit('/?t=' + Date.now())
 * 
 * Without this, tests may use stale JS and pass/fail inconsistently.
 */

describe('Add Item with Cmd+Enter', () => {
    it('creates a new note when pressing Cmd+Enter in idle state', () => {
      // Set up intercepts before visiting
      cy.intercept('POST', '/api/notes/new').as('createNote')
      
      // Visit the page with cache buster
      cy.visit('/?t=' + Date.now())
      
      // Wait for page to fully load
      cy.wait(500)
      
      // Trigger keyboard event directly on document
      cy.document().trigger('keydown', {
        key: 'Enter',
        keyCode: 13,
        which: 13,
        metaKey: true,
        ctrlKey: false,
        bubbles: true,
        cancelable: true
      })
      
      // Wait for note creation
      cy.wait('@createNote')
        .then((interception) => {
          const noteId = interception.response.body.id
          
          // Set up update intercept
          cy.intercept('PUT', `/api/notes/${noteId}/save`).as('updateNote')
          
          // Verify we're in editing mode on the new note
          cy.get('.note.editing', { timeout: 10000 }).should('exist')
          
          // Type content and exit edit mode
          cy.get('.note.editing .note-content')
            .should('have.attr', 'contenteditable', 'true')
          
          cy.get('.note.editing .note-content')
            .focus()
          
          cy.get('.note.editing .note-content')
            .clear()
          
          cy.get('.note.editing .note-content')
            .type('note created with cmd+enter key', { delay: 10 })
          
          // Wait a bit to ensure typing is complete, then save
          cy.wait(200)
          cy.get('.note.editing .note-content')
            .type('{esc}')
          
          // Wait for update
          cy.wait('@updateNote')
          
          // Verify content
          cy.get('.note').should('contain', 'note created with cmd+enter key')
        })
    })
})