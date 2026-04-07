describe('Undo selection after delete', () => {
  it('restores then exits edit mode on the second undo', () => {
    cy.resetTestState()

    cy.intercept('POST', '/api2/notes/view').as('view')
    cy.intercept('POST', '/api2/notes/new').as('createRoot')
    cy.intercept('POST', '/api2/notes/new-child/*').as('createChild')
    cy.intercept('POST', '/api2/notes/*/collapse').as('collapse')
    cy.intercept('DELETE', '/api2/notes/*').as('deleteNote')
    cy.intercept('POST', '/api2/notes/undo*').as('undo')

    cy.clearLocalStorage()
    cy.visitApp('/')
    cy.wait('@view')

    cy.get('#search-input').should('exist').focus().type('aa{enter}')
    cy.wait('@createRoot').then((interception) => {
      expect(interception.response).to.exist
      expect(interception.response.body).to.have.property('id')
      cy.wrap(interception.response.body.id).as('noteId')
    })

    cy.get('@noteId').then((noteId) => {
      cy.get(`[data-note-id="${noteId}"]`, { timeout: 10000 }).should('have.class', 'editing')
    })

    // Make the root note collapsible by giving it a child, then collapse it.
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

    cy.get('@noteId').then((noteId) => {
      cy.get(`[data-note-id="${noteId}"] > .note-collapse-toggle`, { timeout: 10000 })
        .should('exist')
        .click()
    })
    cy.wait('@collapse')
    cy.get('@noteId').then((noteId) => {
      cy.get(`[data-note-id="${noteId}"]`, { timeout: 10000 }).should('have.class', 'collapsed')
    })

    // Select the collapsed note; it auto-expands into edit mode.
    cy.get('@noteId').then((noteId) => {
      cy.get(`[data-note-id="${noteId}"] > .note-content`, { timeout: 10000 }).click()
    })
    cy.get('@noteId').then((noteId) => {
      cy.get(`[data-note-id="${noteId}"]`, { timeout: 10000 })
        .should('have.class', 'editing')
        .and('not.have.class', 'collapsed')
    })

    cy.get('body').type('{meta}{backspace}')
    cy.wait('@deleteNote')
    cy.wait('@view')

    // After delete+refresh the search input may be focused; Cmd+Z is ignored inside inputs.
    cy.get('#notes-container').click('topLeft', { force: true })

    cy.get('body').type('{meta}z')
    cy.wait('@undo')
    cy.wait('@view')
    cy.get('@noteId').then((noteId) => {
      cy.get(`[data-note-id="${noteId}"]`, { timeout: 10000 }).should('have.class', 'editing')
    })

    cy.get('body').type('{meta}z')
    cy.wait('@undo')
    cy.wait('@view')
    cy.get('.note.editing', { timeout: 10000 }).should('not.exist')
    cy.get('@noteId').then((noteId) => {
      cy.get(`[data-note-id="${noteId}"]`, { timeout: 10000 }).should('have.class', 'collapsed')
    })
  })
})
