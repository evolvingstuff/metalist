describe('Paste sibling applies search context', () => {
  it('keeps pasted note visible by adding required tag + text comment', () => {
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

    cy.visitApp('/')
    cy.wait('@initialView')

    cy.get('#search-input').should('exist').focus().type('asdf{enter}')
    cy.wait('@createRoot').then((interception) => {
      expect(interception.response).to.exist
      expect(interception.response.body).to.have.property('id')
      cy.wrap(interception.response.body.id).as('rootNoteId')
    })

    cy.document().trigger('keydown', {
      key: 'Enter',
      keyCode: 13,
      which: 13,
      metaKey: true,
      ctrlKey: false,
      shiftKey: true,
      bubbles: true,
      cancelable: true,
    })
    cy.wait('@createChild')

    cy.get('.note.editing .note-content', { timeout: 10000 })
      .should('exist')
      .click()
      .type('foo bar')

    cy.get('@rootNoteId').then((rootNoteId) => {
      cy.get(`[data-note-id="${rootNoteId}"] > .note-content`).should('exist').click()
    })
    cy.wait('@saveNote')

    cy.document().trigger('keydown', {
      key: 'Enter',
      keyCode: 13,
      which: 13,
      metaKey: true,
      ctrlKey: false,
      shiftKey: true,
      bubbles: true,
      cancelable: true,
    })
    cy.wait('@createChild')

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

    cy.get('#search-input').should('exist').focus().type('{selectall}asdf "foo bar"')
    cy.wait('@viewTagAndTextSearch')

    cy.get('@rootNoteId').then((rootNoteId) => {
      cy.get(`[data-note-id="${rootNoteId}"] > .note-content`).should('exist').click()
    })

    cy.document().trigger('keydown', {
      key: 'v',
      keyCode: 86,
      which: 86,
      metaKey: true,
      ctrlKey: false,
      shiftKey: false,
      bubbles: true,
      cancelable: true,
    })

    cy.wait('@pasteSibling')
    cy.get('.note.editing .note-tag-bar-input', { timeout: 10000 })
      .should('exist')
      .and('have.value', 'asdf /*foo bar*/')
  })
})
