/**
 * IMPORTANT: Always use cache busting when visiting pages in tests.
 * This ensures we get fresh JS files and don't use cached versions:
 * cy.visit('/?t=' + Date.now())
 *
 * Without this, tests may use stale JS and pass/fail inconsistently.
 */

describe('Add Item with Command+Enter', () => {
    it('creates a new note when pressing Command+Enter in idle state', () => {
      // Set up intercepts before visiting
      cy.intercept('POST', '/api/notes/new').as('createNote')

      // Visit the page with cache buster
      cy.visit('/?t=' + Date.now())

      // Wait for page to fully load
      cy.wait(500)

      // Trigger keyboard event directly on document
      cy.document().trigger('keydown', {
        key: 'Enter',
        keyCode: 13,
        which: 13,
        metaKey: true,
        ctrlKey: false,
        bubbles: true,
        cancelable: true
      })

      // Wait for note creation
      cy.wait('@createNote')
        .then((interception) => {
          const noteId = interception.response.body.id

          // Set up update intercept
          cy.intercept('PUT', `/api/notes/${noteId}/save`).as('updateNote')

          // Wait for the note to be in editing mode
          cy.get('.note.editing', { timeout: 10000 }).should('exist')

          // Wait for edit mode to fully settle before typing
          cy.wait(200)

          // Type in note and press Escape to save
          cy.get('.note.editing .note-content')
            .should('have.attr', 'contenteditable', 'true')
            .type('note created with command+enter key')
          
          // Press Escape to save
          cy.get('.note.editing .note-content')
            .type('{esc}')

          // Wait for update
          cy.wait('@updateNote')

          // Verify content
          cy.get('.note').should('contain', 'note created with command+enter key')
        })
    })
})