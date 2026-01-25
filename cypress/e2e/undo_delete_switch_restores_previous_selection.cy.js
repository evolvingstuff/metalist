describe('Undo after switching selection and deleting', () => {
  it('restores the prior selected note on the second undo', () => {
    cy.resetTestState()

    cy.intercept('POST', '/api2/notes/view').as('view')
    cy.intercept('POST', '/api2/notes/new').as('createRoot')
    cy.intercept('POST', '/api2/notes/edit-mode').as('editMode')
    cy.intercept('DELETE', '/api2/notes/*').as('deleteNote')
    cy.intercept('POST', '/api2/notes/undo*').as('undo')

    cy.visitApp('/')
    cy.wait('@view')

    cy.get('body').click(0, 0, { force: true })
    cy.get('body').type('{enter}')
    cy.wait('@createRoot').then((interception) => {
      expect(interception.response).to.exist
      expect(interception.response.body).to.have.property('id')
      cy.wrap(interception.response.body.id).as('noteAId')
    })
    cy.wait('@editMode')
    cy.wait('@view')

    cy.get('body').type('{esc}')
    cy.wait('@editMode')
    cy.wait('@view')

    cy.get('body').type('{enter}')
    cy.wait('@createRoot').then((interception) => {
      expect(interception.response).to.exist
      expect(interception.response.body).to.have.property('id')
      cy.wrap(interception.response.body.id).as('noteBId')
    })
    cy.wait('@editMode')
    cy.wait('@view')

    cy.get('body').type('{esc}')
    cy.wait('@editMode')
    cy.wait('@view')

    cy.get('@noteAId').then((noteAId) => {
      cy.get(`[data-note-id="${noteAId}"] > .note-content`, { timeout: 10000 }).click()
    })
    cy.wait('@editMode')
    cy.wait('@view')

    cy.get('@noteBId').then((noteBId) => {
      cy.get(`[data-note-id="${noteBId}"] > .note-content`, { timeout: 10000 }).click()
    })
    cy.wait('@editMode')
    cy.wait('@view')

    cy.get('body').type('{meta}{backspace}')
    cy.wait('@deleteNote')
    cy.wait('@view')

    // Ensure Cmd-Z is handled as an app shortcut (not by the search input).
    cy.get('#notes-container').click('topLeft', { force: true })

    cy.get('body').type('{meta}z')
    cy.wait('@undo')
    cy.wait('@view')
    cy.get('@noteBId').then((noteBId) => {
      cy.get(`[data-note-id="${noteBId}"]`, { timeout: 10000 }).should('have.class', 'editing')
    })

    cy.get('body').type('{meta}z')
    cy.wait('@undo')
    cy.wait('@view')
    cy.get('@noteAId').then((noteAId) => {
      cy.get(`[data-note-id="${noteAId}"]`, { timeout: 10000 }).should('have.class', 'editing')
    })
  })
})
