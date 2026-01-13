describe('Search negative text terms', () => {
  it('redacts notes containing forbidden quoted text', () => {
    cy.intercept('POST', '/api2/notes/view', (req) => {
      if (req.body && req.body.search === '-"AAB"') {
        req.alias = 'viewNegativeSearch'
      }
    }).as('view')

    cy.intercept('POST', '/api2/notes/new').as('createRoot')
    cy.intercept('POST', '/api2/notes/new-child/*').as('createChild')
    cy.intercept('PUT', '/api2/notes/*/save').as('saveNote')

    cy.visitApp('/')
    cy.wait('@view')

    cy.get('#search-input').should('exist').focus().type('AA{enter}')
    cy.wait('@createRoot').then((interception) => {
      expect(interception.response).to.exist
      expect(interception.response.body).to.have.property('id')
      cy.wrap(interception.response.body.id).as('rootNoteId')
    })

    cy.get('.note.editing .note-content', { timeout: 10000 })
      .should('exist')
      .click()
      .type('{selectall}AA')

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

    cy.wait('@saveNote')
    cy.wait('@createChild').then((interception) => {
      expect(interception.response).to.exist
      expect(interception.response.body).to.have.property('id')
      cy.wrap(interception.response.body.id).as('childNoteId')
    })

    cy.get('.note.editing .note-content', { timeout: 10000 })
      .should('exist')
      .click()
      .type('{selectall}AAB')

    cy.get('#search-input').should('exist').click()
    cy.wait('@saveNote')

    cy.get('#search-input').focus().type('{selectall}-"AAB"')
    cy.wait('@viewNegativeSearch')

    cy.get('@rootNoteId').then((rootNoteId) => {
      cy.get(`[data-note-id="${rootNoteId}"]`, { timeout: 10000 })
        .should('exist')
        .and('not.have.class', 'search-redacted')
    })

    cy.get('@childNoteId').then((childNoteId) => {
      cy.get(`[data-note-id="${childNoteId}"]`, { timeout: 10000 })
        .should('exist')
        .and('have.class', 'search-redacted')
    })
  })
})

