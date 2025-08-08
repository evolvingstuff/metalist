/**
 * IMPORTANT: Always use cache busting when visiting pages in tests.
 * This ensures we get fresh JS files and don't use cached versions:
 * cy.visit('/?t=' + Date.now())
 * 
 * Without this, tests may use stale JS and pass/fail inconsistently.
 */

describe('Smoke Test', () => {
  it('handles basic note creation and editing', () => {
    // Set up intercepts
    cy.intercept('POST', '/api/notes/new').as('createNote')
    
    // Visit and create note with cache buster
    cy.visit('/?t=' + Date.now())
    cy.get('.add-note').click()
    
    // Wait for note creation
    cy.wait('@createNote')
      .then((interception) => {
        const noteId = interception.response.body.id
        
        // Set up update intercept AFTER we have the note ID
        cy.intercept('PUT', `/api/notes/${noteId}/save`).as('updateNote')
        
        // Wait for the note to be in editing mode
        cy.get('.note.editing', { timeout: 10000 }).should('exist')
        
        // Type in note and press Escape to save
        cy.get('.note.editing .note-content')
          .should('have.attr', 'contenteditable', 'true')
          .type('test note')
          .type('{esc}')  // Press Escape to trigger save
        
        // Wait for update
        cy.wait('@updateNote')
        
        // Verify content
        cy.get('.note').should('contain', 'test note')
      })
  })
})