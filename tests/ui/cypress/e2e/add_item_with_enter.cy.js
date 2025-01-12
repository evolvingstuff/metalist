describe('Add Item with Enter', () => {
    it('creates a new note when pressing Enter in idle state', () => {
      // Set up intercepts before visiting
      cy.intercept('POST', '/api/notes/new').as('createNote')
      
      // Visit the page
      cy.visit('/')
      
      // Press Enter key (in idle state)
      cy.get('#app').type('{enter}')
      
      // Wait for note creation - this should fail since Enter isn't implemented
      cy.wait('@createNote', { timeout: 1000 })
        .then((interception) => {
          const noteId = interception.response.body.id
          
          // Set up update intercept
          cy.intercept('PUT', `/api/notes/${noteId}`).as('updateNote')
          
          // Verify we're in editing mode on the new note
          cy.get('.note.editing').should('exist')
          
          // Type content and exit edit mode
          cy.get('.note.editing .note-content')
            .type('note created with enter key')
            .type('{esc}')
          
          // Wait for update
          cy.wait('@updateNote')
          
          // Verify content
          cy.get('.note').should('contain', 'note created with enter key')
        })
    })
})