describe('Search input Enter key', () => {
  it('creates a new note when Enter is pressed in the search bar', () => {
    cy.intercept('POST', '/api2/notes/view').as('initialView')
    cy.intercept('POST', '/api2/notes/new').as('createNote')

    cy.visitApp('/')

    cy.wait('@initialView')

    cy.get('#search-input').should('exist').focus().type('asdf{enter}')

    cy.wait('@createNote')
    cy.get('.note.editing', { timeout: 10000 }).should('exist')
    cy.get('.note.editing .note-tag-bar-input', { timeout: 10000 })
      .should('exist')
      .and('have.value', 'asdf')
  })
})
