/**
 * Undo/redo should traverse edit-mode transitions + content edits in order.
 *
 * Scenario:
 * 1) Select note (S0)
 * 2) Edit note (S1)
 * 3) Exit editing
 * 4) Undo -> re-enter editing at S1
 * 5) Undo -> still editing, now S0
 * 6) Undo -> exit editing
 * 7) Redo -> editing at S0
 * 8) Redo -> editing at S1
 * 9) Redo -> exit editing
 */

describe('Undo/Redo includes edit-mode transitions', () => {
  it('restores editing state and content snapshots across Cmd+Z/Cmd+Y', () => {
    cy.intercept('POST', '/api2/notes/new').as('createNote')

    cy.visit('/?t=' + Date.now())

    cy.get('#app', { timeout: 10000 }).should('have.class', 'loaded')

    cy.get('.add-note').click()

    cy.wait('@createNote', { timeout: 10000 }).then((interception) => {
      const noteId = interception.response.body.id

      cy.intercept('PUT', `/api2/notes/${noteId}/save`).as('saveNote')
      cy.intercept('POST', '/api2/notes/edit-mode', (req) => {
        if (!req.body || typeof req.body !== 'object') {
          return
        }
        const before = req.body.beforeEditingNoteId
        const after = req.body.afterEditingNoteId
        if (before === null && after === noteId) {
          req.alias = 'enterEditMode'
        }
        if (before === noteId && after === null) {
          req.alias = 'exitEditMode'
        }
      })

      // Seed a note body (content doesn't matter for this test)
      cy.get('.note.editing .note-content')
        .should('have.attr', 'contenteditable', 'true')
        .type('seed')
        .type('{esc}')

      cy.wait('@saveNote', { timeout: 10000 })
      cy.wait('@exitEditMode', { timeout: 10000 })
      cy.get('.note.editing').should('not.exist')

      cy.get(`.note[data-note-id="${noteId}"] .note-content`).click()
      cy.wait('@enterEditMode', { timeout: 10000 })

      // Change tags only (S1)
      cy.get('.note.editing .note-tag-bar-input')
        .should('have.attr', 'type', 'text')
        .clear()
        .type('t1')

      cy.document().trigger('keydown', {
        key: 'p',
        code: 'KeyP',
        keyCode: 80,
        which: 80,
        metaKey: true,
        ctrlKey: false,
        bubbles: true,
        cancelable: true,
      })

      cy.wait('@saveNote', { timeout: 10000 })
      cy.wait('@exitEditMode', { timeout: 10000 })

      cy.get('#password-modal', { timeout: 10000 }).should('be.visible')
      cy.get('#cancel-btn', { timeout: 10000 }).click()
      cy.get('#password-modal').should('not.be.visible')

      cy.intercept('POST', '/api2/notes/undo*').as('undo')
      cy.intercept('POST', '/api2/notes/redo*').as('redo')

      cy.document().trigger('keydown', {
        key: 'z',
        code: 'KeyZ',
        keyCode: 90,
        which: 90,
        metaKey: true,
        ctrlKey: false,
        bubbles: true,
        cancelable: true,
      })
      cy.wait('@undo', { timeout: 10000 })
      cy.get('.note.editing .note-tag-bar-input')
        .invoke('val')
        .then((value) => {
          expect((value || '').trim()).to.eq('t1')
        })

      cy.document().trigger('keydown', {
        key: 'z',
        code: 'KeyZ',
        keyCode: 90,
        which: 90,
        metaKey: true,
        ctrlKey: false,
        bubbles: true,
        cancelable: true,
      })
      cy.wait('@undo', { timeout: 10000 })
      cy.get('.note.editing .note-tag-bar-input')
        .invoke('val')
        .then((value) => {
          expect((value || '').trim()).to.eq('')
        })

      cy.document().trigger('keydown', {
        key: 'z',
        code: 'KeyZ',
        keyCode: 90,
        which: 90,
        metaKey: true,
        ctrlKey: false,
        bubbles: true,
        cancelable: true,
      })
      cy.wait('@undo', { timeout: 10000 })
      cy.get('.note.editing').should('not.exist')

      cy.document().trigger('keydown', {
        key: 'y',
        code: 'KeyY',
        keyCode: 89,
        which: 89,
        metaKey: true,
        ctrlKey: false,
        bubbles: true,
        cancelable: true,
      })
      cy.wait('@redo', { timeout: 10000 })
      cy.get('.note.editing .note-tag-bar-input')
        .invoke('val')
        .then((value) => {
          expect((value || '').trim()).to.eq('')
        })

      cy.document().trigger('keydown', {
        key: 'y',
        code: 'KeyY',
        keyCode: 89,
        which: 89,
        metaKey: true,
        ctrlKey: false,
        bubbles: true,
        cancelable: true,
      })
      cy.wait('@redo', { timeout: 10000 })
      cy.get('.note.editing .note-tag-bar-input')
        .invoke('val')
        .then((value) => {
          expect((value || '').trim()).to.eq('t1')
        })

      cy.document().trigger('keydown', {
        key: 'y',
        code: 'KeyY',
        keyCode: 89,
        which: 89,
        metaKey: true,
        ctrlKey: false,
        bubbles: true,
        cancelable: true,
      })
      cy.wait('@redo', { timeout: 10000 })
      cy.get('.note.editing').should('not.exist')
    })
  })
})
