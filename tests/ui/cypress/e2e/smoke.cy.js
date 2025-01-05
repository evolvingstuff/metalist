describe('Smoke Test', () => {
  it('handles basic note creation and editing', () => {
    // Set up intercepts
    cy.intercept('POST', '/api/notes/new').as('createNote')
    
    // Visit and create note
    cy.visit('/')
    cy.get('.add-note').click()
    
    // Wait for note creation
    cy.wait('@createNote')
      .then((interception) => {
        const noteId = interception.response.body.id
        
        // Set up update intercept AFTER we have the note ID
        cy.intercept('PUT', `/api/notes/${noteId}`).as('updateNote')
        
        // Type in note and press Escape to save
        cy.get('.note.editing .note-content')
          .type('test note')
          .type('{esc}')  // Press Escape to trigger save
        
        // Wait for update
        cy.wait('@updateNote')
        
        // Verify content
        cy.get('.note').should('contain', 'test note')
      })
  })
})