/**
 * Verify caret position enters at end when editing a note.
 */

describe('Caret position behavior', () => {
  it('places caret at end when re-entering edit mode', () => {
    cy.intercept('POST', '/api/notes/new').as('createNote');
    cy.visit('/?t=' + Date.now());
    cy.get('.add-note').click();

    cy.wait('@createNote').then((interception) => {
      const noteId = interception.response.body.id;
      cy.intercept('PUT', `/api/notes/${noteId}/save`).as('saveNote');

      cy.get('.note.editing .note-content')
        .should('have.attr', 'contenteditable', 'true')
        .type('hello')
        .type('{esc}');

      cy.wait('@saveNote');
      cy.get(`.note[data-note-id="${noteId}"]`).should('contain', 'hello');

      cy.get(`.note[data-note-id="${noteId}"] .note-content`).click();
      cy.get('.note.editing .note-content')
        .should('have.attr', 'contenteditable', 'true')
        .type('X')
        .type('{esc}');

      cy.wait('@saveNote');
      cy.get(`.note[data-note-id="${noteId}"]`).should('contain', 'helloX');
    });
  });
});
