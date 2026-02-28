describe('Collapsed note preview', () => {
  it('normalizes oversized markdown heading formatting to a single visible line', () => {
    cy.intercept('POST', '/api2/notes/view').as('view')
    cy.intercept('POST', '/api2/notes/new').as('createNote')
    cy.intercept('PUT', '/api2/notes/*/save').as('saveNote')
    cy.intercept('POST', '/api2/notes/*/collapse').as('collapseNote')

    cy.visitApp('/')
    cy.wait('@view')

    cy.get('#search-input').should('exist').focus().type('preview{enter}')
    cy.wait('@createNote').then((interception) => {
      expect(interception.response).to.exist
      expect(interception.response.body).to.have.property('id')
      cy.wrap(interception.response.body.id).as('noteId')
    })

    cy.get('.note.editing .note-content', { timeout: 10000 })
      .should('exist')
      .click()
      .type('# OpenMemory{enter}Long-term memory for AI systems.')

    cy.get('.note.editing .note-tag-bar-input', { timeout: 10000 })
      .should('exist')
      .clear()
      .type('@markdown')

    cy.get('#search-input').click()
    cy.wait('@saveNote')
    cy.get('.note.editing', { timeout: 10000 }).should('not.exist')

    cy.get('@noteId').then((noteId) => {
      const noteSelector = `[data-note-id="${noteId}"]`
      const noteContentSelector = `${noteSelector} > .note-content`

      cy.get(noteSelector, { timeout: 10000 })
        .should('have.attr', 'data-can-collapse', 'true')
      cy.get(`${noteContentSelector} .meta-markdown`, { timeout: 10000 }).should('exist')

      cy.get(`${noteSelector} > .note-collapse-toggle`, { timeout: 10000 }).click()
      cy.wait('@collapseNote')

      cy.get(noteSelector, { timeout: 10000 }).should('have.class', 'collapsed')

      cy.get(noteContentSelector, { timeout: 10000 }).should(($noteContent) => {
        const noteContentElement = $noteContent[0]
        const browserWindow = noteContentElement.ownerDocument.defaultView
        if (!browserWindow) {
          throw new Error('window is unavailable for collapsed preview style assertions')
        }
        const noteContentStyle = browserWindow.getComputedStyle(noteContentElement)
        const headingElement = noteContentElement.querySelector('.meta-markdown h1')
        if (!(headingElement instanceof browserWindow.HTMLElement)) {
          throw new Error('expected markdown heading in collapsed note preview')
        }
        const headingStyle = browserWindow.getComputedStyle(headingElement)

        expect(noteContentElement.getBoundingClientRect().height).to.be.lessThan(40)
        expect(headingStyle.marginTop).to.equal('0px')
        expect(headingStyle.fontSize).to.equal(noteContentStyle.fontSize)
      })

      cy.get(noteContentSelector).should('contain.text', 'OpenMemory')
    })
  })
})
