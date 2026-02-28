describe('Collapse affordance for parents with children', () => {
  it('keeps the expand toggle visible after collapsing', () => {
    cy.resetTestState()

    cy.intercept('POST', '/api2/notes/view').as('view')
    cy.intercept('POST', '/api2/notes/new').as('createRoot')
    cy.intercept('POST', '/api2/notes/new-child/*').as('createChild')
    cy.intercept('POST', '/api2/notes/*/collapse').as('collapse')
    cy.intercept('POST', '/api2/notes/*/expand').as('expand')
    cy.intercept('POST', '/api2/notes/edit-mode').as('editMode')

    cy.clearLocalStorage()
    cy.visitApp('/')
    cy.wait('@view')

    cy.get('#search-input').should('exist').focus().type('parent{enter}')
    cy.wait('@createRoot').then((interception) => {
      expect(interception.response).to.exist
      expect(interception.response.body).to.have.property('id')
      cy.wrap(interception.response.body.id).as('parentNoteId')
    })
    cy.wait('@editMode')

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

    // Exit edit mode so collapse/expand only affects the tree view.
    cy.get('#search-input').click()
    cy.get('.note.editing', { timeout: 10000 }).should('not.exist')

    cy.get('@parentNoteId').then((parentNoteId) => {
      cy.get(`[data-note-id="${parentNoteId}"]`, { timeout: 10000 })
        .should('have.attr', 'data-can-collapse', 'true')

      cy.get(`[data-note-id="${parentNoteId}"] > .note-collapse-toggle`, { timeout: 10000 })
        .should('have.css', 'display', 'flex')
        .click()
    })
    cy.wait('@collapse')

    cy.get('@parentNoteId').then((parentNoteId) => {
      cy.get(`[data-note-id="${parentNoteId}"]`, { timeout: 10000 }).should('have.class', 'collapsed')

      // Regression: collapsed parents with children must still show an expand control.
      cy.get(`[data-note-id="${parentNoteId}"]`, { timeout: 10000 })
        .should('have.attr', 'data-can-collapse', 'true')
    })

    cy.reload()
    cy.wait('@view')

    cy.get('@parentNoteId').then((parentNoteId) => {
      cy.get(`[data-note-id="${parentNoteId}"]`, { timeout: 10000 })
        .should('have.class', 'collapsed')
        .and('have.attr', 'data-can-collapse', 'true')
      cy.get(`[data-note-id="${parentNoteId}"] > .note-collapse-toggle`, { timeout: 10000 })
        .should('have.css', 'display', 'flex')
        .click()
    })

    cy.wait('@expand')

    cy.get('@parentNoteId').then((parentNoteId) => {
      cy.get(`[data-note-id="${parentNoteId}"]`, { timeout: 10000 }).should('not.have.class', 'collapsed')
    })

    cy.get('@childNoteId').then((childNoteId) => {
      cy.get(`[data-note-id="${childNoteId}"]`, { timeout: 10000 }).should('exist')
    })
  })
})
