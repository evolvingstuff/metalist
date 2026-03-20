function triggerMetaEnter({ shiftKey }) {
  cy.document().trigger('keydown', {
    key: 'Enter',
    keyCode: 13,
    which: 13,
    metaKey: true,
    ctrlKey: false,
    shiftKey,
    bubbles: true,
    cancelable: true,
  })
}

describe('Search redacted note reveal', () => {
  it('reveals all redacted portions in the same note subtree without moving the nearby visible note', () => {
    let visibleNoteTopBefore = 0

    cy.intercept('POST', '/api2/notes/view', (req) => {
      if (req.body && req.body.search === '-"AAB"') {
        req.alias = 'viewNegativeSearch'
      }
    }).as('view')
    cy.intercept('POST', '/api2/notes/new').as('createRoot')
    cy.intercept('POST', '/api2/notes/new-child/*').as('createChild')
    cy.intercept('POST', '/api2/notes/new-sibling/*').as('createSibling')
    cy.intercept('PUT', '/api2/notes/*/save').as('saveNote')

    cy.visitApp('/')
    cy.wait('@view')

    cy.get('#search-input').should('exist').focus().type('AA{enter}')
    cy.wait('@createRoot')

    cy.get('.note.editing .note-content', { timeout: 10000 })
      .should('exist')
      .click()
      .type('{selectall}root')

    triggerMetaEnter({ shiftKey: true })

    cy.wait('@createChild').then((interception) => {
      expect(interception.response).to.exist
      expect(interception.response.body).to.have.property('id')
      cy.wrap(interception.response.body.id).as('redactedNoteOneId')
    })
    cy.wait('@saveNote')

    cy.get('.note.editing .note-content', { timeout: 10000 })
      .should('exist')
      .click()
      .type('{selectall}AAB{enter}line two{enter}line three{enter}line four{enter}line five')

    triggerMetaEnter({ shiftKey: false })

    cy.wait('@createSibling').then((interception) => {
      expect(interception.response).to.exist
      expect(interception.response.body).to.have.property('id')
      cy.wrap(interception.response.body.id).as('redactedNoteTwoId')
    })
    cy.wait('@saveNote')

    cy.get('.note.editing .note-content', { timeout: 10000 })
      .should('exist')
      .click()
      .type('{selectall}AAB second child')

    triggerMetaEnter({ shiftKey: false })

    cy.wait('@createSibling').then((interception) => {
      expect(interception.response).to.exist
      expect(interception.response.body).to.have.property('id')
      cy.wrap(interception.response.body.id).as('visibleNoteId')
    })
    cy.wait('@saveNote')

    cy.get('.note.editing .note-content', { timeout: 10000 })
      .should('exist')
      .click()
      .type('{selectall}visible child')

    cy.get('#search-input').should('exist').click()
    cy.wait('@saveNote')

    cy.get('#search-input').focus().type('{selectall}-"AAB"')
    cy.wait('@viewNegativeSearch')

    cy.get('@redactedNoteOneId').then((redactedNoteId) => {
      cy.get(`[data-note-id="${redactedNoteId}"]`, { timeout: 10000 })
        .should('exist')
        .and('have.class', 'search-redacted')
    })

    cy.get('@redactedNoteTwoId').then((redactedNoteId) => {
      cy.get(`[data-note-id="${redactedNoteId}"]`, { timeout: 10000 })
        .should('exist')
        .and('have.class', 'search-redacted')
    })

    cy.get('@visibleNoteId').then((visibleNoteId) => {
      cy.get(`[data-note-id="${visibleNoteId}"]`, { timeout: 10000 })
        .should('exist')
        .and('not.have.class', 'search-redacted')
        .then(($note) => {
          visibleNoteTopBefore = $note[0].getBoundingClientRect().top
        })
    })

    cy.get('@redactedNoteOneId').then((redactedNoteId) => {
      cy.get(`[data-note-id="${redactedNoteId}"] .note-content`, { timeout: 10000 })
        .click()
    })

    cy.wait(100)
    cy.get('#search-input').should('have.value', '-"AAB"')

    cy.get('@redactedNoteOneId').then((redactedNoteId) => {
      cy.get(`[data-note-id="${redactedNoteId}"]`, { timeout: 10000 })
        .should('have.class', 'search-revealed')
        .and('not.have.class', 'search-redacted')
      cy.get(`[data-note-id="${redactedNoteId}"] .note-content`)
        .then(($content) => {
          expect($content[0].getBoundingClientRect().height).to.be.greaterThan(20)
        })
    })

    cy.get('@redactedNoteTwoId').then((redactedNoteId) => {
      cy.get(`[data-note-id="${redactedNoteId}"]`, { timeout: 10000 })
        .should('have.class', 'search-revealed')
        .and('not.have.class', 'search-redacted')
    })

    cy.get('@visibleNoteId').then((visibleNoteId) => {
      cy.get(`[data-note-id="${visibleNoteId}"]`, { timeout: 10000 })
        .then(($note) => {
          const visibleNoteTopAfter = $note[0].getBoundingClientRect().top
          expect(Math.abs(visibleNoteTopAfter - visibleNoteTopBefore)).to.be.lessThan(4)
        })
    })
  })
})
