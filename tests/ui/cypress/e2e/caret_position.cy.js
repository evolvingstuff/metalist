/**
 * Verify caret position enters at end when editing a note.
 */

describe('Caret position behavior', () => {
  it('places caret at end when re-entering edit mode', () => {
    cy.intercept('POST', '/api/notes/new').as('createNote');
    cy.intercept('GET', '/api/notes/view*').as('loadNotes');
    cy.visit('/?t=' + Date.now());
    cy.wait('@loadNotes');
    cy.get('#app', { timeout: 10000 }).should('have.class', 'loaded');
    cy.get('.add-note').should('be.visible').click();

    cy.wait('@createNote', { timeout: 10000 }).then((interception) => {
      const noteId = interception.response.body.id;
      cy.intercept('PUT', `/api/notes/${noteId}/save`).as('saveNote');

      cy.get('.note.editing .note-content')
        .should('have.attr', 'contenteditable', 'true')
        .type('hello')
        .type('{esc}');

      cy.wait('@saveNote');
      cy.get(`.note[data-note-id="${noteId}"]`).should('contain', 'hello');

      cy.get(`.note[data-note-id="${noteId}"] .note-content`).click();
      cy.assertCaretAtEnd('.note.editing .note-content');

      cy.get('.note.editing .note-content')
        .type('X')
        .type('{esc}');

      cy.wait('@saveNote', { timeout: 10000 });
      cy.get(`.note[data-note-id="${noteId}"]`).should('contain', 'helloX');
    });
  });
});
