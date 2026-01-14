describe('Paste sibling applies inherited tags', () => {
  it('adds inherited non-meta tags to the pasted root note', () => {
    cy.intercept('POST', '/api2/notes/view').as('initialView')
    cy.intercept('POST', '/api2/notes/new').as('createRoot')
    cy.intercept('POST', '/api2/notes/new-child/*').as('createChild')
    cy.intercept('PUT', '/api2/notes/*/save').as('saveNote')
    cy.intercept('POST', '/api2/notes/*/copy').as('copyNote')
    cy.intercept('POST', '/api2/notes/paste-sibling/*').as('pasteSibling')

    cy.visitApp('/')
    cy.wait('@initialView')

    cy.get('#search-input').should('exist').focus().type('asdf{enter}')
    cy.wait('@createRoot')

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
    cy.wait('@createChild')

    cy.get('.note.editing .note-content', { timeout: 10000 })
      .should('exist')
      .click()
      .type('child content')

    cy.document().trigger('keydown', {
      key: 'c',
      keyCode: 67,
      which: 67,
      metaKey: true,
      ctrlKey: false,
      shiftKey: false,
      bubbles: true,
      cancelable: true,
    })

    cy.wait('@saveNote')
    cy.wait('@copyNote')

    cy.get('.note.editing')
      .should('exist')
      .invoke('attr', 'data-parent-id')
      .then((parentId) => {
        expect(parentId).to.be.a('string').and.not.equal('')
        cy.get(`[data-note-id="${parentId}"] > .note-content`).should('exist').click()
      })

    cy.document().trigger('keydown', {
      key: 'v',
      keyCode: 86,
      which: 86,
      metaKey: true,
      ctrlKey: false,
      shiftKey: false,
      bubbles: true,
      cancelable: true,
    })

    cy.wait('@pasteSibling')
    cy.get('.note.editing .note-tag-bar-input', { timeout: 10000 })
      .should('exist')
      .and('have.value', 'asdf')
  })
})
