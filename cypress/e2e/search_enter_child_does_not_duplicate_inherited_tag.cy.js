describe('Search tag inheritance on child creation', () => {
  it('does not duplicate inherited non-meta tags on child notes', () => {
    cy.intercept('POST', '/api2/notes/view').as('initialView')
    cy.intercept('POST', '/api2/notes/new').as('createRoot')
    cy.intercept('POST', '/api2/notes/new-child/*').as('createChild')

    cy.visitApp('/')
    cy.wait('@initialView')

    cy.get('#search-input').should('exist').focus().type('asdf{enter}')
    cy.wait('@createRoot')

    cy.get('.note.editing .note-tag-bar-input', { timeout: 10000 })
      .should('exist')
      .and('have.value', 'asdf')

    cy.get('.note.editing .note-content').should('exist').click()

    cy.document().trigger('keydown', {
      key: 'Enter',
      keyCode: 13,
      which: 13,
      metaKey: true,
      ctrlKey: false,
      shiftKey: true,
      bubbles: true,
      cancelable: true,
    })

    cy.wait('@createChild')
    cy.get('.note.editing .note-tag-bar-input', { timeout: 10000 })
      .should('exist')
      .and('have.value', '')
  })
})

