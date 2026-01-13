describe('Collapse shortcut (Space)', () => {
  it('does not toggle collapse when hovering an unselected note', () => {
    let collapseCalls = 0
    let expandCalls = 0

    cy.intercept('POST', '/api2/notes/view').as('initialView')
    cy.intercept('POST', '/api2/notes/new').as('createRoot')
    cy.intercept('PUT', '/api2/notes/*/save').as('saveNote')

    cy.intercept('POST', '/api2/notes/*/collapse', (req) => {
      collapseCalls += 1
      req.continue()
    }).as('collapseNote')

    cy.intercept('POST', '/api2/notes/*/expand', (req) => {
      expandCalls += 1
      req.continue()
    }).as('expandNote')

    cy.visitApp('/')
    cy.wait('@initialView')

    cy.get('#search-input').should('exist').focus().type('aa{enter}')
    cy.wait('@createRoot').then((interception) => {
      expect(interception.response).to.exist
      expect(interception.response.body).to.have.property('id')
      cy.wrap(interception.response.body.id).as('noteId')
    })

    cy.get('.note.editing .note-content', { timeout: 10000 })
      .should('exist')
      .click()
      .type('{selectall}line one{enter}line two')

    cy.document().trigger('keydown', {
      key: 'Escape',
      keyCode: 27,
      which: 27,
      bubbles: true,
      cancelable: true,
    })
    cy.wait('@saveNote')

    cy.get('.note.editing').should('not.exist')

    cy.get('@noteId').then((noteId) => {
      const noteSelector = `[data-note-id="${noteId}"]`
      const noteContentSelector = `${noteSelector} > .note-content`

      cy.get(noteSelector, { timeout: 10000 })
        .should('exist')
        .and('have.attr', 'data-is-collapsed', 'false')
        .and('have.attr', 'data-can-collapse', 'true')
        .and('not.have.class', 'collapsed')

      cy.get(noteContentSelector).trigger('mouseover', { force: true })
      cy.document().trigger('keydown', {
        key: ' ',
        code: 'Space',
        keyCode: 32,
        which: 32,
        bubbles: true,
        cancelable: true,
      })

      cy.wait(500)

      cy.then(() => {
        expect(collapseCalls).to.eq(0)
        expect(expandCalls).to.eq(0)
      })

      cy.get(noteSelector)
        .should('have.attr', 'data-is-collapsed', 'false')
        .and('not.have.class', 'collapsed')
    })
  })
})

