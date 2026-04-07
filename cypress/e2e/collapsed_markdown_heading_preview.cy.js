describe('Collapsed note preview', () => {
  it('normalizes oversized markdown heading formatting to a single visible line', () => {
    cy.resetTestState()

    cy.intercept('POST', '/api2/notes/view').as('view')
    cy.intercept('POST', '/api2/notes/new').as('createNote')
    cy.intercept('POST', '/api2/notes/edit-mode').as('editMode')
    cy.intercept('PUT', '/api2/notes/*/save').as('saveNote')
    cy.intercept('POST', '/api2/notes/*/collapse').as('collapseNote')

    cy.clearLocalStorage()
    cy.visitApp('/')
    cy.wait('@view')

    cy.get('#search-input').should('exist').focus().type('preview{enter}')
    cy.wait('@createNote').then((interception) => {
      expect(interception.response).to.exist
      expect(interception.response.body).to.have.property('id')
      cy.wrap(interception.response.body.id).as('noteId')
    })
    cy.wait('@editMode')

    cy.get('.note.editing .note-content', { timeout: 10000 })
      .should('exist')
      .click()
      .type('# OpenMemory{enter}Long-term memory for AI systems.')

    cy.get('.note.editing .note-tag-bar-input', { timeout: 10000 })
      .should('exist')
      .clear()
      .type('@markdown preview')

    cy.get('#notes-container').click('bottomRight', { force: true })
    cy.wait('@saveNote')
    cy.get('.note.editing', { timeout: 10000 }).should('not.exist')
    cy.wait('@view')
    cy.get('@noteId').then((noteId) => {
      const noteSelector = `[data-note-id="${noteId}"]`
      const noteContentSelector = `${noteSelector} > .note-content`

      cy.get(noteSelector, { timeout: 10000 })
        .should('have.attr', 'data-can-collapse', 'true')
      cy.get(`${noteContentSelector} .meta-markdown`, { timeout: 10000 }).should('exist')

      cy.window().then((win) => {
        const token = win.localStorage.getItem('auth_token')
        const tabId = win.sessionStorage.getItem('metalist_tab_id')
        const clientId = win.sessionStorage.getItem('metalist_client_id')
        const undoContextEpoch = win.sessionStorage.getItem('metalist_undo_context_epoch') ?? '0'
        const searchInput = win.document.getElementById('search-input')
        if (!(searchInput instanceof win.HTMLInputElement)) {
          throw new Error('search input missing before collapse request')
        }
        if (!token || !tabId || !clientId) {
          throw new Error('missing auth/session state for collapse request')
        }

        return cy.request({
          method: 'POST',
          url: `/api2/notes/${noteId}/collapse`,
          headers: {
            Authorization: `Bearer ${token}`,
            'X-Metalist-Tab-Id': tabId,
          },
          body: {
            clientId,
            undoContext: `tab:0|search:${searchInput.value}|epoch:${undoContextEpoch}`,
            viewport: {
              scrollY: Math.max(0, Math.round(win.scrollY)),
              scrollAnchor: null,
            },
          },
        }).its('status').should('eq', 200)
      })
      cy.reload()
      cy.wait('@view')

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
    })
  })
})
