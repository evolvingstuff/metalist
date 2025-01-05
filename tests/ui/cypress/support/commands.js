// Custom commands for our note app

// Example command to create a new note with content
Cypress.Commands.add('createNote', (content) => {
  cy.get('.add-note').click()
  if (content) {
    cy.get('.note.editing .note-content').type(content)
  }
})

// Example command to verify note state
Cypress.Commands.add('noteState', (state) => {
  cy.get('.note').should('have.class', state)
}) 