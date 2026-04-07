describe('Undo selection on collapsed notes', () => {
  it('does not require an extra undo after auto-expanding on select', () => {
    cy.resetTestState()

    cy.intercept('POST', '/api2/notes/view').as('view')
    cy.intercept('POST', '/api2/notes/new').as('createRoot')
    cy.intercept('POST', '/api2/notes/new-child/*').as('createChild')
    cy.intercept('POST', '/api2/notes/*/collapse').as('collapse')
    cy.intercept('POST', '/api2/notes/undo*').as('undo')

    cy.clearLocalStorage()
    cy.visitApp('/')
    cy.wait('@view')

    cy.get('#search-input').should('exist').focus().type('aa{enter}')
    cy.wait('@createRoot').then((interception) => {
      expect(interception.response).to.exist
      expect(interception.response.body).to.have.property('id')
      cy.wrap(interception.response.body.id).as('parentNoteId')
    })

    cy.get('body').trigger('keydown', {
      key: 'Enter',
      keyCode: 13,
      which: 13,
      metaKey: true,
      shiftKey: true,
      bubbles: true,
      cancelable: true,
    })
    cy.wait('@createChild').then((interception) => {
      expect(interception.response).to.exist
      expect(interception.response.body).to.have.property('id')
      cy.wrap(interception.response.body.id).as('childNoteId')
    })
    cy.get('@childNoteId').then((childNoteId) => {
      cy.get(`[data-note-id="${childNoteId}"]`, { timeout: 10000 }).should('have.class', 'editing')
    })

    cy.get('body').trigger('keydown', {
      key: 'Escape',
      keyCode: 27,
      which: 27,
      bubbles: true,
      cancelable: true,
    })
    cy.get('.note.editing', { timeout: 10000 }).should('not.exist')

    cy.get('@parentNoteId').then((parentNoteId) => {
      cy.get(`[data-note-id="${parentNoteId}"] > .note-collapse-toggle`, { timeout: 10000 })
        .should('exist')
        .click()
    })
    cy.wait('@collapse')

    cy.get('@parentNoteId').then((parentNoteId) => {
      cy.get(`[data-note-id="${parentNoteId}"]`, { timeout: 10000 }).should('have.class', 'collapsed')

      cy.get(`[data-note-id="${parentNoteId}"] > .note-content`).click()
    })

    cy.get('@parentNoteId').then((parentNoteId) => {
      cy.get(`[data-note-id="${parentNoteId}"]`, { timeout: 10000 })
        .should('have.class', 'editing')
        .should('not.have.class', 'collapsed')
    })

    cy.get('body').type('{meta}z')
    cy.wait('@undo')
    cy.wait('@view')
    cy.get('.note.editing', { timeout: 10000 }).should('not.exist')
    cy.get('@parentNoteId').then((parentNoteId) => {
      cy.get(`[data-note-id="${parentNoteId}"]`, { timeout: 10000 }).should('have.class', 'collapsed')
    })
  })
})
