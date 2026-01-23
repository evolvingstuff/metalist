describe('Undo selection after delete', () => {
  it('restores the previously selected note after undoing a delete', () => {
    cy.resetTestState()

    cy.intercept('POST', '/api2/notes/view').as('initialView')
    cy.intercept('POST', '/api2/notes/new').as('createRoot')
    cy.intercept('POST', '/api2/notes/new-sibling/*').as('createSibling')
    cy.intercept('POST', '/api2/notes/*/move').as('moveNote')
    cy.intercept('DELETE', '/api2/notes/*').as('deleteNote')
    cy.intercept('POST', '/api2/notes/undo*').as('undo')

    cy.clearLocalStorage()
    cy.visitApp('/')
    cy.wait('@initialView')

    cy.get('body').type('{meta}{enter}')
    cy.wait('@createRoot').then((interception) => {
      expect(interception.response).to.exist
      expect(interception.response.body).to.have.property('id')
      cy.wrap(interception.response.body.id).as('noteIdA')
    })

    cy.get('body').type('{meta}{enter}')
    cy.wait('@createSibling').then((interception) => {
      expect(interception.response).to.exist
      expect(interception.response.body).to.have.property('id')
      cy.wrap(interception.response.body.id).as('noteIdB')
    })

    cy.get('@noteIdA').then((noteIdA) => {
      cy.get(`[data-note-id="${noteIdA}"] > .note-content`, { timeout: 10000 }).click()
      cy.get(`[data-note-id="${noteIdA}"]`, { timeout: 10000 }).should('have.class', 'editing')
    })

    cy.get('body').trigger('keydown', {
      key: 'ArrowDown',
      keyCode: 40,
      which: 40,
      metaKey: true,
      bubbles: true,
      cancelable: true,
    })
    cy.wait('@moveNote')

    cy.get('@noteIdB').then((noteIdB) => {
      cy.get(`[data-note-id="${noteIdB}"] > .note-content`, { timeout: 10000 }).click()
      cy.get(`[data-note-id="${noteIdB}"]`, { timeout: 10000 }).should('have.class', 'editing')
    })

    cy.get('body').trigger('keydown', {
      key: 'Backspace',
      keyCode: 8,
      which: 8,
      metaKey: true,
      bubbles: true,
      cancelable: true,
    })
    cy.wait('@deleteNote')

    cy.get('body').type('{meta}z')
    cy.wait('@undo')
    cy.get('@noteIdB').then((noteIdB) => {
      cy.get(`[data-note-id="${noteIdB}"]`, { timeout: 10000 }).should('have.class', 'editing')
    })

    cy.get('body').type('{meta}z')
    cy.wait('@undo')
    cy.get('@noteIdA').then((noteIdA) => {
      cy.get(`[data-note-id="${noteIdA}"]`, { timeout: 10000 }).should('have.class', 'editing')
    })
  })
})

