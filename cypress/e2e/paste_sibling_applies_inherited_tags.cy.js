describe('Paste sibling applies search context', () => {
  it('keeps pasted note visible by adding required tag + text comment', () => {
    const triggerCreateChildFromEditingTagBar = () => {
      cy.get('.note.editing .note-tag-bar-input', { timeout: 10000 })
        .should('exist')
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
    }

    cy.resetTestState()

    cy.intercept('POST', '/api2/notes/view', (req) => {
      if (req.body && req.body.search === 'asdf "foo bar"') {
        req.alias = 'viewTagAndTextSearch'
      }
    }).as('initialView')
    cy.intercept('POST', '/api2/notes/new').as('createRoot')
    cy.intercept('POST', '/api2/notes/new-child/*').as('createChild')
    cy.intercept('PUT', '/api2/notes/*/save').as('saveNote')
    cy.intercept('POST', '/api2/notes/*/copy').as('copyNote')
    cy.intercept('POST', '/api2/notes/paste-sibling/*').as('pasteSibling')

    cy.clearLocalStorage()
    cy.visitApp('/')
    cy.wait('@initialView')

    cy.get('#search-input').should('exist').focus().type('asdf{enter}')
    cy.wait('@createRoot').then((interception) => {
      expect(interception.response).to.exist
      expect(interception.response.body).to.have.property('id')
      cy.wrap(interception.response.body.id).as('rootNoteId')
    })

    cy.get('@rootNoteId').then((rootNoteId) => {
      cy.get(`[data-note-id="${rootNoteId}"] > .note-content`, { timeout: 10000 })
        .should('exist')
        .click()
        .type('foo bar')
    })

    triggerCreateChildFromEditingTagBar()
    cy.wait('@createChild').then((interception) => {
      expect(interception.response).to.exist
      expect(interception.response.body).to.have.property('id')
      cy.wrap(interception.response.body.id).as('copiedNoteId')
    })

    cy.get('.note.editing .note-tag-bar-input', { timeout: 10000 })
      .should('exist')
      .and('have.value', '')

    cy.get('.note.editing .note-content', { timeout: 10000 })
      .should('exist')
      .click()
      .type('Inner note!')

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

    cy.reload()
    cy.wait('@initialView')

    cy.get('body').should('not.have.class', 'loading')
    cy.get('#search-input').should('exist').clear()
    cy.get('#search-input').type('asdf "foo bar"', { parseSpecialCharSequences: false })
    cy.wait('@viewTagAndTextSearch')

    cy.get('@rootNoteId').then((rootNoteId) => {
      cy.get(`[data-note-id="${rootNoteId}"] > .note-content`, { timeout: 10000 }).should('exist').click()
      cy.get(`[data-note-id="${rootNoteId}"]`, { timeout: 10000 }).should('have.class', 'editing')
      cy.window().then((win) => {
        const token = win.localStorage.getItem('auth_token')
        const tabId = win.sessionStorage.getItem('metalist_tab_id')
        const clientId = win.sessionStorage.getItem('metalist_client_id')
        const undoContextEpoch = win.sessionStorage.getItem('metalist_undo_context_epoch') ?? '0'
        const searchInput = win.document.getElementById('search-input')
        if (!(searchInput instanceof win.HTMLInputElement)) {
          throw new Error('search input missing before paste request')
        }
        if (!token || !tabId || !clientId) {
          throw new Error('missing auth/session state for paste request')
        }

        return cy.request({
          method: 'POST',
          url: `/api2/notes/paste-sibling/${rootNoteId}`,
          headers: {
            Authorization: `Bearer ${token}`,
            'X-Metalist-Tab-Id': tabId,
          },
          body: {
            search_query: searchInput.value,
            clientId,
            undoContext: `tab:0|search:${searchInput.value}|epoch:${undoContextEpoch}`,
            viewport: {
              scrollY: Math.max(0, Math.round(win.scrollY)),
              scrollAnchor: null,
            },
          },
        }).then((response) => {
          expect(response.status).to.eq(200)
          expect(response.body).to.have.property('id')
          cy.wrap(response.body.id).as('pastedNoteId')
        })
      })
    })

    cy.reload()
    cy.wait('@initialView')
    cy.get('body').should('not.have.class', 'loading')
    cy.get('#search-input').should('have.value', 'asdf "foo bar"')

    cy.get('@pastedNoteId').then((pastedNoteId) => {
      cy.get(`[data-note-id="${pastedNoteId}"] > .note-content`, { timeout: 10000 }).should('exist').click()
    })
    cy.get('.note.editing .note-tag-bar-input', { timeout: 10000 })
      .should('exist')
      .and('have.value', 'asdf /*foo bar*/')
  })
})
