describe('Search negative text terms', () => {
  it('redacts notes containing forbidden quoted text', () => {
    const triggerMetaEnter = ({ shiftKey }) => {
      cy.document().trigger('keydown', {
        key: 'Enter',
        keyCode: 13,
        which: 13,
        metaKey: true,
        ctrlKey: false,
        shiftKey,
        bubbles: true,
        cancelable: true,
      })
    }

    cy.intercept('POST', '/api2/notes/view', (req) => {
      if (req.body && req.body.search === 'AA -"AAB"') {
        req.alias = 'viewNegativeSearch'
      }
    }).as('view')

    cy.intercept('POST', '/api2/notes/new').as('createRoot')
    cy.intercept('POST', '/api2/notes/new-child/*').as('createChild')
    cy.intercept('POST', '/api2/notes/new-sibling/*').as('createSibling')
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
      .type('{selectall}root')

    triggerMetaEnter({ shiftKey: true })
    cy.wait('@createChild').then((interception) => {
      expect(interception.response).to.exist
      expect(interception.response.body).to.have.property('id')
      cy.wrap(interception.response.body.id).as('redactedNoteId')
    })
    cy.wait('@saveNote')

    cy.get('@redactedNoteId').then((redactedNoteId) => {
      cy.get(`[data-note-id="${redactedNoteId}"] > .note-content`, { timeout: 10000 })
        .click()
        .type('{selectall}AAB{enter}line two{enter}line three{enter}line four{enter}line five')
    })

    triggerMetaEnter({ shiftKey: false })
    cy.wait('@createSibling').then((interception) => {
      expect(interception.response).to.exist
      expect(interception.response.body).to.have.property('id')
      cy.wrap(interception.response.body.id).as('visibleNoteId')
    })
    cy.wait('@saveNote')

    cy.get('@visibleNoteId').then((visibleNoteId) => {
      cy.get(`[data-note-id="${visibleNoteId}"] > .note-content`, { timeout: 10000 })
        .click()
        .type('{selectall}visible child')
    })

    cy.get('#search-input').should('exist').click()
    cy.wait('@saveNote')

    cy.get('#search-input').focus().type('{selectall}{backspace}')
    cy.get('#search-input').type('AA -"AAB"', { parseSpecialCharSequences: false })
    cy.wait('@viewNegativeSearch')

    cy.get('@redactedNoteId').then((redactedNoteId) => {
      cy.get(`[data-note-id="${redactedNoteId}"]`, { timeout: 10000 })
        .should('exist')
        .and('have.class', 'search-redacted')
    })

    cy.get('@visibleNoteId').then((visibleNoteId) => {
      cy.get(`[data-note-id="${visibleNoteId}"]`, { timeout: 10000 })
        .should('exist')
        .and('not.have.class', 'search-redacted')
    })
  })
})
