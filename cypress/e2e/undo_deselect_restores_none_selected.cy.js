describe('Undo selection/deselection', () => {
  it('undoes selection back to none-selected state', () => {
    cy.resetTestState()

    const tag = 'sel'

    cy.intercept('POST', '/api2/notes/view').as('view')
    cy.intercept('POST', '/api2/notes/new').as('createRoot')
    cy.intercept('POST', '/api2/notes/edit-mode').as('editMode')
    cy.intercept('POST', '/api2/notes/undo*').as('undo')

    cy.visitApp('/')
    cy.wait('@view')

    cy.get('#search-input').should('exist').focus().type(`${tag}{enter}`)
    cy.wait('@createRoot').then((interception) => {
      expect(interception.response).to.exist
      expect(interception.response.body).to.have.property('id')
      cy.wrap(interception.response.body.id).as('noteAId')
    })
    cy.wait('@editMode')

    // Deselect so the next create is a root note.
    cy.get('body').type('{esc}')
    cy.wait('@editMode')

    cy.get('#search-input').focus().type('{enter}')
    cy.wait('@createRoot').then((interception) => {
      expect(interception.response).to.exist
      expect(interception.response.body).to.have.property('id')
      cy.wrap(interception.response.body.id).as('noteBId')
    })
    cy.wait('@editMode')

    cy.get('body').type('{esc}')
    cy.wait('@editMode')

    // Reload with a new clientId so undo stack only contains the selection ops below,
    // while keeping the non-empty search context to avoid infinite-scroll throwing.
    cy.window().then((win) => {
      win.sessionStorage.removeItem('metalist_client_id')
    })
    cy.reload()
    cy.wait('@view')

    cy.get('@noteAId').then((noteAId) => {
      cy.get(`[data-note-id="${noteAId}"] > .note-content`, { timeout: 10000 }).click()
    })
    cy.wait('@editMode')
    cy.get('body').type('{esc}')
    cy.wait('@editMode')

    cy.get('@noteBId').then((noteBId) => {
      cy.get(`[data-note-id="${noteBId}"] > .note-content`, { timeout: 10000 }).click()
    })
    cy.wait('@editMode')
    cy.get('body').type('{esc}')
    cy.wait('@editMode')

    cy.get('.note.editing').should('not.exist')

    cy.get('body').type('{meta}z')
    cy.wait('@undo')
    cy.wait('@view')
    cy.get('@noteBId').then((noteBId) => {
      cy.get('.note.editing', { timeout: 10000 })
        .should('exist')
        .should('have.attr', 'data-note-id', noteBId)
    })

    cy.get('body').type('{meta}z')
    cy.wait('@undo')
    cy.wait('@view')
    cy.get('.note.editing', { timeout: 10000 }).should('not.exist')
  })
})
