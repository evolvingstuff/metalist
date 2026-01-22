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
})

