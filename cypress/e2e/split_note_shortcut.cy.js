function triggerSplitShortcut() {
  cy.document().trigger('keydown', {
    key: 's',
    keyCode: 83,
    which: 83,
    metaKey: true,
    ctrlKey: false,
    shiftKey: false,
    bubbles: true,
    cancelable: true,
  })
}

function selectTextOffsetsInEditingNote(startOffset, endOffset) {
  cy.get('.note.editing .note-content', { timeout: 10000 }).then(($content) => {
    const content = $content[0]
    cy.window().then((win) => {
      const doc = win.document
      const walker = doc.createTreeWalker(content, win.NodeFilter.SHOW_TEXT)
      const textNode = walker.nextNode()
      expect(textNode, 'editing note text node').to.exist
      const range = doc.createRange()
      range.setStart(textNode, startOffset)
      range.setEnd(textNode, endOffset)
      const selection = win.getSelection()
      expect(selection, 'window selection').to.exist
      selection.removeAllRanges()
      selection.addRange(range)
    })
  })
}

function selectAllTextInEditingNote() {
  cy.get('.note.editing .note-content', { timeout: 10000 }).then(($content) => {
    const content = $content[0]
    cy.window().then((win) => {
      const doc = win.document
      const range = doc.createRange()
      range.selectNodeContents(content)
      const selection = win.getSelection()
      expect(selection, 'window selection').to.exist
      selection.removeAllRanges()
      selection.addRange(range)
    })
  })
}

function placeCaretAtEndOfEditingNote() {
  cy.get('.note.editing .note-content', { timeout: 10000 }).then(($content) => {
    const content = $content[0]
    cy.window().then((win) => {
      const doc = win.document
      const range = doc.createRange()
      range.selectNodeContents(content)
      range.collapse(false)
      const selection = win.getSelection()
      expect(selection, 'window selection').to.exist
      selection.removeAllRanges()
      selection.addRange(range)
    })
  })
}

function assertNoteTextAndTagAtIndex(index, expectedText, expectedTag) {
  cy.get('.note').eq(index).find('> .note-content').click()
  cy.get('.note.editing .note-content', { timeout: 10000 }).should('contain.text', expectedText)
  cy.get('.note.editing .note-tag-bar-input', { timeout: 10000 }).should('have.value', expectedTag)
}

describe('Split shortcut (Cmd+S)', () => {
  it('splits around a selected segment and preserves tags on all split notes', () => {
    cy.intercept('POST', '/api2/notes/view').as('initialView')
    cy.intercept('POST', '/api2/notes/new').as('createRoot')
    cy.intercept('POST', '/api2/notes/new-sibling/*').as('createSibling')
    cy.intercept('PUT', '/api2/notes/*/save').as('saveNote')

    cy.visitApp('/')
    cy.wait('@initialView')

    cy.get('#search-input').focus().type('{enter}')
    cy.wait('@createRoot')

    cy.get('.note.editing .note-tag-bar-input', { timeout: 10000 })
      .should('exist')
      .clear()
      .type('alpha')

    cy.get('.note.editing .note-content', { timeout: 10000 })
      .click()
      .type('foo bar baz')

    selectTextOffsetsInEditingNote(4, 7)
    triggerSplitShortcut()

    cy.wait('@saveNote')
    cy.wait('@createSibling')
    cy.wait('@saveNote')
    cy.wait('@createSibling')
    cy.wait('@saveNote')

    cy.get('.note').should('have.length', 3)
    assertNoteTextAndTagAtIndex(0, 'foo', 'alpha')
    assertNoteTextAndTagAtIndex(1, 'bar', 'alpha')
    assertNoteTextAndTagAtIndex(2, 'baz', 'alpha')
  })

  it('does nothing when all text is selected', () => {
    cy.intercept('POST', '/api2/notes/view').as('initialView')
    cy.intercept('POST', '/api2/notes/new').as('createRoot')
    cy.intercept('POST', '/api2/notes/new-sibling/*').as('createSibling')

    cy.visitApp('/')
    cy.wait('@initialView')

    cy.get('#search-input').focus().type('{enter}')
    cy.wait('@createRoot')

    cy.get('.note.editing .note-content', { timeout: 10000 })
      .click()
      .type('foo bar baz')

    selectAllTextInEditingNote()
    triggerSplitShortcut()

    cy.wait(250)
    cy.get('.note').should('have.length', 1)
    cy.get('.note.editing .note-content').should('contain.text', 'foo bar baz')
    cy.get('@createSibling.all').should('have.length', 0)
  })

  it('does nothing when caret is at the end of the note', () => {
    cy.intercept('POST', '/api2/notes/view').as('initialView')
    cy.intercept('POST', '/api2/notes/new').as('createRoot')
    cy.intercept('POST', '/api2/notes/new-sibling/*').as('createSibling')

    cy.visitApp('/')
    cy.wait('@initialView')

    cy.get('#search-input').focus().type('{enter}')
    cy.wait('@createRoot')

    cy.get('.note.editing .note-content', { timeout: 10000 })
      .click()
      .type('foo bar baz')

    placeCaretAtEndOfEditingNote()
    triggerSplitShortcut()

    cy.wait(250)
    cy.get('.note').should('have.length', 1)
    cy.get('.note.editing .note-content').should('contain.text', 'foo bar baz')
    cy.get('@createSibling.all').should('have.length', 0)
  })
})
