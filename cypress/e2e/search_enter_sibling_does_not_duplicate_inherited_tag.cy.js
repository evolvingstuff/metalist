describe('Search tag inheritance on sibling creation', () => {
  it('does not duplicate inherited non-meta tags on sibling notes', () => {
    cy.intercept('POST', '/api2/notes/view').as('initialView')
    cy.intercept('POST', '/api2/notes/new').as('createRoot')
    cy.intercept('POST', '/api2/notes/new-child/*').as('createChild')
    cy.intercept('POST', '/api2/notes/new-sibling/*').as('createSibling')

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

    cy.get('.note.editing .note-tag-bar-input', { timeout: 10000 })
      .focus()
      .trigger('keydown', {
      key: 'Enter',
      keyCode: 13,
      which: 13,
      metaKey: true,
      ctrlKey: false,
      shiftKey: false,
      bubbles: true,
      cancelable: true,
    })

    cy.wait('@createSibling').then((interception) => {
      expect(interception.response).to.exist
      expect(interception.response.body).to.have.property('id')
      cy.wrap(interception.response.body.id).as('siblingNoteId')
    })

    cy.get('#search-input').focus().type('{selectall}{backspace}')
    cy.wait('@initialView')

    cy.get('.note').should('have.length', 3)
    cy.get('@siblingNoteId').then((siblingNoteId) => {
      cy.get(`[data-note-id="${siblingNoteId}"] > .note-content`, { timeout: 10000 }).click()
    })
    cy.get('.note.editing .note-tag-bar-input', { timeout: 10000 }).should('have.value', '')
  })
})
