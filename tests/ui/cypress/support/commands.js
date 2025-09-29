// Custom commands for our note app

// Example command to create a new note with content
Cypress.Commands.add('createNote', (content) => {
  cy.get('.add-note').click()
  if (content) {
    cy.get('.note.editing .note-content').type(content)
  }
})

// Example command to verify note state
Cypress.Commands.add('noteState', (state) => {
  cy.get('.note').should('have.class', state)
}) 

// Assert that the caret is positioned at the end of a contenteditable element
Cypress.Commands.add('assertCaretAtEnd', (selector) => {
  cy.get(selector)
    .should('have.attr', 'contenteditable', 'true')
    .then(($el) => {
      const element = $el.get(0)
      const doc = element?.ownerDocument
      const selection = doc?.getSelection?.()

      expect(element, 'contenteditable element').to.exist
      expect(selection, 'document selection').to.exist
      expect(selection.rangeCount, 'selection range count').to.be.greaterThan(0)

      const range = selection.getRangeAt(0)

      expect(range.collapsed, 'caret selection collapsed').to.be.true
      expect(element.contains(range.endContainer), 'caret inside element').to.be.true

      const measureRange = doc.createRange()
      measureRange.selectNodeContents(element)
      measureRange.setEnd(range.endContainer, range.endOffset)

      const caretOffset = measureRange.toString().length
      const textLength = element.textContent.length

      if (typeof measureRange.detach === 'function') {
        measureRange.detach()
      }

      expect(caretOffset, 'caret offset').to.equal(textLength)
    })
})
