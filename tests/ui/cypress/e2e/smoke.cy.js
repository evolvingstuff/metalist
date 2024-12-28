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
        
        // Set up update intercept
        cy.intercept('PUT', `/api/notes/${noteId}`).as('updateNote')
        
        // Type in note
        cy.get('.note.editing .note-content').type('test note')
        
        // Wait for update
        cy.wait('@updateNote')
        
        // Verify and signal completion
        cy.get('.note').should('contain', 'test note')
          .then(() => {
            cy.task('testComplete')
          })
      })
  })
})