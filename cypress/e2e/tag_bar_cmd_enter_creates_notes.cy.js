describe('Tag bar shortcuts for note creation', () => {
  it('creates a sibling note when Cmd-Enter is pressed while the tag bar is focused', () => {
    cy.intercept('POST', '/api2/notes/view').as('initialView')
    cy.intercept('POST', '/api2/notes/new').as('createRoot')
    cy.intercept('POST', '/api2/notes/new-sibling/*').as('createSibling')
    cy.intercept('PUT', '/api2/notes/*/save').as('saveNote')

    cy.visitApp('/')
    cy.wait('@initialView')

    cy.get('#search-input').should('exist').focus().type('asdf{enter}')
    cy.wait('@createRoot')

    cy.get('.note').should('have.length', 1)
    cy.get('.note.editing .note-tag-bar-input', { timeout: 10000 })
      .should('exist')
      .clear()
      .type('alpha')
      .focus()
      .trigger('keydown', {
        key: 'Enter',
        keyCode: 13,
        which: 13,
        metaKey: true,
        ctrlKey: false,
        shiftKey: false,
        bubbles: true,
        cancelable: true,
      })

    cy.wait('@saveNote')
    cy.wait('@createSibling')
    cy.get('.note').should('have.length', 2)
    cy.get('.note').eq(0).find('> .note-content').click()
    cy.get('.note.editing .note-tag-bar-input', { timeout: 10000 }).should('have.value', 'alpha')
  })

  it('creates a child note when Cmd-Shift-Enter is pressed while the tag bar is focused', () => {
    cy.intercept('POST', '/api2/notes/view').as('initialView')
    cy.intercept('POST', '/api2/notes/new').as('createRoot')
    cy.intercept('POST', '/api2/notes/new-child/*').as('createChild')
    cy.intercept('PUT', '/api2/notes/*/save').as('saveNote')

    cy.visitApp('/')
    cy.wait('@initialView')

    cy.get('#search-input').should('exist').focus().type('asdf{enter}')
    cy.wait('@createRoot')

    cy.get('.note').should('have.length', 1)
    cy.get('.note.editing .note-tag-bar-input', { timeout: 10000 })
      .should('exist')
      .clear()
      .type('alpha')
      .focus()
      .trigger('keydown', {
        key: 'Enter',
        keyCode: 13,
        which: 13,
        metaKey: true,
        ctrlKey: false,
        shiftKey: true,
        bubbles: true,
        cancelable: true,
      })

    cy.wait('@saveNote')
    cy.wait('@createChild')
    cy.get('.note').should('have.length', 2)
    cy.get('.note-children .note').should('exist')
    cy.get('.note').eq(0).find('> .note-content').click()
    cy.get('.note.editing .note-tag-bar-input', { timeout: 10000 }).should('have.value', 'alpha')
  })
})
