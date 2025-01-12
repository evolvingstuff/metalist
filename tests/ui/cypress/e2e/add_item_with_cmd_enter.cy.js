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

      // Press Command+Enter key (in idle state)
      cy.get('body').type('{cmd+enter}')

      // Wait for note creation
      cy.wait('@createNote')
        .then((interception) => {
          const noteId = interception.response.body.id

          // Set up update intercept
          cy.intercept('PUT', `/api/notes/${noteId}`).as('updateNote')

          // Type in note and press Escape to save
          cy.get('.note.editing .note-content')
            .type('note created with command+enter key')
            .type('{esc}')

          // Wait for update
          cy.wait('@updateNote')

          // Verify content
          cy.get('.note').should('contain', 'note created with command+enter key')
        })
    })
})