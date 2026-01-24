describe('Command palette', () => {
  it('opens with Cmd+/ and toggles Show tags in list', () => {
    cy.intercept('POST', '/api2/notes/view').as('initialView')

    cy.clearLocalStorage()
    cy.visitApp('/')
    cy.wait('@initialView')

    cy.get('body').type('{meta}/')
    cy.get('#command-palette-modal').should('be.visible')
    cy.get('#command-palette-input').should('be.focused').type('tags {enter}')

    cy.get('body').should('have.class', 'pref-show-note-tags')
    cy.get('#command-palette-modal').should('be.visible')

    cy.get('#command-palette-input').type('{esc}')
    cy.get('#command-palette-modal').should('not.be.visible')
  })

  it('resets undo stack boundary on open', () => {
    cy.resetTestState()

    cy.intercept('POST', '/api2/notes/view').as('view')
    cy.intercept('POST', '/api2/notes/new').as('createRoot')
    cy.intercept('POST', '/api2/notes/edit-mode').as('editMode')
    cy.intercept('POST', '/api2/notes/undo*').as('undo')

    cy.visitApp('/')
    cy.wait('@view')

    cy.get('#search-input').should('exist').focus().type('palette-reset{enter}')
    cy.wait('@createRoot')
    cy.wait('@editMode')

    // Create an undo entry.
    cy.get('body').type('{esc}')
    cy.wait('@editMode')

    cy.get('body').type('{meta}/')
    cy.get('#command-palette-modal').should('be.visible')

    // Close the palette so global keyboard shortcuts are active.
    cy.get('#command-palette-input').type('{esc}')
    cy.get('#command-palette-modal').should('not.be.visible')

    // Ensure we're not in editing mode; otherwise Cmd-Z is handled by contenteditable.
    cy.get('.note.editing', { timeout: 10000 }).should('not.exist')

    cy.get('body').type('{meta}z')
    cy.wait('@undo').then((interception) => {
      expect(interception.response).to.exist
      expect(interception.response.body).to.have.property('status', 'noop')
    })
  })
})
