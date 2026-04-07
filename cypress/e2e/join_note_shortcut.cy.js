function triggerJoinShortcut() {
  cy.document().trigger('keydown', {
    key: 'j',
    keyCode: 74,
    which: 74,
    metaKey: true,
    ctrlKey: false,
    shiftKey: false,
    bubbles: true,
    cancelable: true,
  })
}

describe('Join shortcut (Cmd+J)', () => {
  it('joins selected note with its next sibling and merges tags', () => {
    cy.resetTestState()

    cy.intercept('POST', '/api2/notes/view').as('initialView')
    cy.intercept('POST', '/api2/notes/new').as('createRoot')
    cy.intercept('POST', '/api2/notes/new-sibling/*').as('createSibling')
    cy.intercept('POST', '/api2/notes/*/join-next').as('joinNext')

    cy.clearLocalStorage()
    cy.visitApp('/')
    cy.wait('@initialView')

    cy.get('#search-input').focus().type('{enter}')
    cy.wait('@createRoot')

    cy.get('.note.editing .note-tag-bar-input', { timeout: 10000 })
      .clear()
    cy.get('.note.editing .note-tag-bar-input', { timeout: 10000 }).type('alpha')
    cy.get('.note.editing .note-content', { timeout: 10000 })
      .click()
      .type('foo')

    cy.document().trigger('keydown', {
      key: 'Enter',
      keyCode: 13,
      which: 13,
      metaKey: true,
      ctrlKey: false,
      shiftKey: false,
      bubbles: true,
      cancelable: true,
    })
    cy.wait('@createSibling')
    cy.get('.note.editing .note-tag-bar-input', { timeout: 10000 }).should('exist')

    cy.get('.note.editing .note-tag-bar-input', { timeout: 10000 })
      .clear()
    cy.get('.note.editing .note-tag-bar-input', { timeout: 10000 }).type('beta')
    cy.get('.note.editing .note-content', { timeout: 10000 })
      .click()
      .type('bar')

    cy.get('.note').eq(0).find('> .note-content').click()
    triggerJoinShortcut()

    cy.wait('@joinNext')
    cy.get('.note').should('have.length', 1)
    cy.get('.note.editing .note-content').should('contain.text', 'foo').and('contain.text', 'bar')
    cy.get('.note.editing .note-tag-bar-input').should('have.value', 'alpha beta')
  })

  it('no-ops when there is no next sibling', () => {
    cy.resetTestState()

    cy.intercept('POST', '/api2/notes/view').as('initialView')
    cy.intercept('POST', '/api2/notes/new').as('createRoot')
    cy.intercept('POST', '/api2/notes/*/join-next').as('joinNext')

    cy.clearLocalStorage()
    cy.visitApp('/')
    cy.wait('@initialView')

    cy.get('#search-input').focus().type('{enter}')
    cy.wait('@createRoot')

    cy.get('.note.editing .note-content', { timeout: 10000 })
      .click()
      .type('solo')

    triggerJoinShortcut()

    cy.wait('@joinNext')
    cy.get('@joinNext.all').should('have.length', 1)
    cy.get('.note').should('have.length', 1)
    cy.get('.note.editing .note-content').should('contain.text', 'solo')
  })
})
