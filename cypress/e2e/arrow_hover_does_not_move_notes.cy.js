describe('Move shortcuts (ArrowUp/ArrowDown)', () => {
  it('does not move notes when hovering an unselected note', () => {
    let moveCalls = 0
    const triggerCreateSiblingShortcut = () => {
      cy.get('.note.editing .note-tag-bar-input', { timeout: 10000 })
        .should('exist')
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
    }

    cy.intercept('POST', '/api2/notes/view').as('initialView')
    cy.intercept('POST', '/api2/notes/new').as('createRoot')
    cy.intercept('POST', '/api2/notes/new-sibling/*').as('createSibling')

    cy.intercept('POST', '/api2/notes/*/move', (req) => {
      moveCalls += 1
      req.continue()
    }).as('moveNote')

    cy.visitApp('/')
    cy.wait('@initialView')

    cy.get('#search-input').should('exist').focus().type('aa{enter}')
    cy.wait('@createRoot').then((interception) => {
      expect(interception.response).to.exist
      expect(interception.response.body).to.have.property('id')
      cy.wrap(interception.response.body.id).as('noteId1')
    })

    triggerCreateSiblingShortcut()
    cy.wait('@createSibling').then((interception) => {
      expect(interception.response).to.exist
      expect(interception.response.body).to.have.property('id')
      cy.wrap(interception.response.body.id).as('noteId2')
    })
    cy.get('@noteId2').then((noteId2) => {
      cy.get(`[data-note-id="${noteId2}"]`, { timeout: 10000 }).should('have.class', 'editing')
    })

    triggerCreateSiblingShortcut()
    cy.wait('@createSibling').then((interception) => {
      expect(interception.response).to.exist
      expect(interception.response.body).to.have.property('id')
      cy.wrap(interception.response.body.id).as('noteId3')
    })

    cy.get('@noteId2').then((noteId2) => {
      const hoveredSelector = `[data-note-id="${noteId2}"]`
      cy.get(hoveredSelector, { timeout: 10000 }).should('exist')

      cy.get(`${hoveredSelector} > .note-content`)
        .trigger('mouseover', { force: true })
        .trigger('keydown', {
          key: 'ArrowUp',
          keyCode: 38,
          which: 38,
          bubbles: true,
          cancelable: true,
        })
        .trigger('keydown', {
          key: 'ArrowDown',
          keyCode: 40,
          which: 40,
          bubbles: true,
          cancelable: true,
        })

      cy.wait(500)

      cy.then(() => {
        expect(moveCalls).to.eq(0)
      })
    })
  })
})
