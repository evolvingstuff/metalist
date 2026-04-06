function triggerDocumentShortcut({ key, keyCode, which, shiftKey = false }) {
  cy.document().trigger('keydown', {
    key,
    keyCode,
    which,
    metaKey: true,
    ctrlKey: false,
    shiftKey,
    bubbles: true,
    cancelable: true,
  })
}

function triggerFocusedTagBarShortcut({ key, keyCode, which, shiftKey = false }) {
  cy.get('.note.editing .note-tag-bar-input', { timeout: 10000 })
    .should('exist')
    .focus()
    .trigger('keydown', {
      key,
      keyCode,
      which,
      metaKey: true,
      ctrlKey: false,
      shiftKey,
      bubbles: true,
      cancelable: true,
    })
}

describe('Tag bar note-level shortcuts', () => {
  it('moves the current note up and down from the tag bar and preserves edited tags', () => {
    cy.intercept('POST', '/api2/notes/view').as('initialView')
    cy.intercept('POST', '/api2/notes/new').as('createRoot')
    cy.intercept('POST', '/api2/notes/new-sibling/*').as('createSibling')
    cy.intercept('PUT', '/api2/notes/*/save').as('saveNote')
    cy.intercept('POST', '/api2/notes/*/move').as('moveNote')

    cy.visitApp('/')
    cy.wait('@initialView')

    cy.get('#search-input').focus().type('{enter}')
    cy.wait('@createRoot')

    cy.get('.note.editing .note-content', { timeout: 10000 }).click().type('first')

    triggerDocumentShortcut({ key: 'Enter', keyCode: 13, which: 13 })
    cy.wait('@saveNote')
    cy.wait('@createSibling')

    cy.get('.note.editing .note-content', { timeout: 10000 }).click().type('second')
    cy.get('.note.editing .note-tag-bar-input', { timeout: 10000 }).clear().type('urgent')

    triggerFocusedTagBarShortcut({ key: 'ArrowUp', keyCode: 38, which: 38 })

    cy.wait('@saveNote')
    cy.wait('@moveNote')
    cy.get('.note').should('have.length', 2)
    cy.get('.note').eq(0).find('> .note-content').should('contain.text', 'second')
    cy.get('.note.editing .note-tag-bar-input').should('have.value', 'urgent')

    triggerFocusedTagBarShortcut({ key: 'ArrowDown', keyCode: 40, which: 40 })

    cy.wait('@moveNote')
    cy.get('.note').eq(0).find('> .note-content').should('contain.text', 'first')
    cy.get('.note').eq(1).find('> .note-content').should('contain.text', 'second')
    cy.get('.note.editing .note-tag-bar-input').should('have.value', 'urgent')
  })

  it('indents and outdents the current note from the tag bar', () => {
    cy.intercept('POST', '/api2/notes/view').as('initialView')
    cy.intercept('POST', '/api2/notes/new').as('createRoot')
    cy.intercept('POST', '/api2/notes/new-sibling/*').as('createSibling')
    cy.intercept('PUT', '/api2/notes/*/save').as('saveNote')
    cy.intercept('POST', '/api2/notes/*/indent').as('indentNote')
    cy.intercept('POST', '/api2/notes/*/outdent').as('outdentNote')

    cy.visitApp('/')
    cy.wait('@initialView')

    cy.get('#search-input').focus().type('{enter}')
    cy.wait('@createRoot')

    cy.get('.note.editing .note-content', { timeout: 10000 }).click().type('parent')

    triggerDocumentShortcut({ key: 'Enter', keyCode: 13, which: 13 })
    cy.wait('@saveNote')
    cy.wait('@createSibling')

    cy.get('.note.editing .note-content', { timeout: 10000 }).click().type('child')
    cy.get('.note.editing .note-tag-bar-input', { timeout: 10000 }).clear().type('nested')

    triggerFocusedTagBarShortcut({ key: 'ArrowRight', keyCode: 39, which: 39 })

    cy.wait('@saveNote')
    cy.wait('@indentNote')
    cy.get('.note').eq(0).find('> .note-children > .note').should('have.length', 1)
    cy.get('.note').eq(0).find('> .note-children > .note > .note-content').should('contain.text', 'child')
    cy.get('.note.editing .note-tag-bar-input').should('have.value', 'nested')

    triggerFocusedTagBarShortcut({ key: 'ArrowLeft', keyCode: 37, which: 37 })

    cy.wait('@outdentNote')
    cy.get('.note').eq(0).find('> .note-children > .note').should('not.exist')
    cy.get('.note').eq(1).find('> .note-content').should('contain.text', 'child')
    cy.get('.note.editing .note-tag-bar-input').should('have.value', 'nested')
  })

  it('deletes the current note from the tag bar', () => {
    cy.intercept('POST', '/api2/notes/view').as('initialView')
    cy.intercept('POST', '/api2/notes/new').as('createRoot')
    cy.intercept('POST', '/api2/notes/new-sibling/*').as('createSibling')
    cy.intercept('DELETE', '/api2/notes/*').as('deleteNote')

    cy.visitApp('/')
    cy.wait('@initialView')

    cy.get('#search-input').focus().type('{enter}')
    cy.wait('@createRoot')

    cy.get('.note.editing .note-content', { timeout: 10000 }).click().type('keep')

    triggerDocumentShortcut({ key: 'Enter', keyCode: 13, which: 13 })
    cy.wait('@createSibling')

    cy.get('.note.editing .note-content', { timeout: 10000 }).click().type('remove')

    triggerFocusedTagBarShortcut({ key: 'Backspace', keyCode: 8, which: 8 })

    cy.wait('@deleteNote')
    cy.get('.note').should('have.length', 1)
    cy.get('.note.editing .note-content', { timeout: 10000 }).should('contain.text', 'keep')
  })
})
