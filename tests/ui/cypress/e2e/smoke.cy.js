describe('Smoke Test', () => {
  it('can visit the app', () => {
    cy.visit('/')
    cy.get('body').should('exist')
  })

  it('can create a new note', () => {
    cy.visit('/')
    cy.get('.add-note').click()
    // Wait for API response and auto-reload
    cy.intercept('POST', '/api/notes/new').as('createNote')
    cy.wait('@createNote')
  })

  it('handles page reloads', () => {
    cy.visit('/')
    // Create note and intercept the API call
    cy.intercept('POST', '/api/notes/new').as('createNote')
    cy.get('.add-note').click()
    cy.wait('@createNote')
    
    // After auto-reload, type in the new note
    cy.get('.note-content').type('test note')
    
    // Intercept the update API call
    cy.intercept('PUT', '/api/notes/*').as('updateNote')
    cy.wait('@updateNote')
    
    // Manual reload to verify persistence
    cy.reload()
    cy.get('.note').should('contain', 'test note')
  })
}) 