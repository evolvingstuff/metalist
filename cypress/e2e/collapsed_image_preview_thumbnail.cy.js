describe('Collapsed image preview thumbnail', () => {
  it('renders a compact thumbnail when the first image has inline width styles', () => {
    cy.resetTestState()

    cy.intercept('POST', '/api2/notes/view').as('view')
    cy.intercept('POST', '/api2/notes/new').as('createNote')
    cy.intercept('POST', '/api2/notes/edit-mode').as('editMode')
    cy.intercept('PUT', '/api2/notes/*/save').as('saveNote')
    cy.intercept('POST', '/api2/notes/*/collapse').as('collapseNote')

    cy.clearLocalStorage()
    cy.visitApp('/')
    cy.wait('@view')

    cy.get('#search-input').should('exist').focus().type('imagepreview{enter}')
    cy.wait('@createNote').then((interception) => {
      expect(interception.response).to.exist
      expect(interception.response.body).to.have.property('id')
      cy.wrap(interception.response.body.id).as('noteId')
    })
    cy.wait('@editMode')

    cy.get('.note.editing .note-content', { timeout: 10000 }).should('exist').then(($content) => {
      const contentElement = $content[0]
      if (!(contentElement instanceof HTMLElement)) {
        throw new Error('Expected editable note content element')
      }

      const wideSvg = '<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="400"><rect width="1600" height="400" fill="#0f172a"/><rect x="90" y="70" width="1420" height="260" fill="#f8fafc"/></svg>'
      const imageSource = `data:image/svg+xml;utf8,${encodeURIComponent(wideSvg)}`
      contentElement.innerHTML = `<img src="${imageSource}" alt="wide-inline" style="max-width: 100%; width: 100%; height: auto;" /><br/>Second line`
      contentElement.dispatchEvent(new Event('input', { bubbles: true, cancelable: true }))
    })

    cy.get('#search-input').click()
    cy.wait('@saveNote')
    cy.get('.note.editing', { timeout: 10000 }).should('not.exist')

    cy.get('@noteId').then((noteId) => {
      const noteSelector = `[data-note-id="${noteId}"]`
      cy.get(noteSelector, { timeout: 10000 }).should('have.attr', 'data-can-collapse', 'true')
      cy.get(`${noteSelector} > .note-collapse-toggle`, { timeout: 10000 }).click()
    })
    cy.wait('@collapseNote')

    cy.get('@noteId').then((noteId) => {
      const noteSelector = `[data-note-id="${noteId}"]`
      const imageSelector = `${noteSelector} > .note-content img`
      cy.get(noteSelector, { timeout: 10000 }).should('have.class', 'collapsed')
      cy.get(imageSelector, { timeout: 10000 }).should(($img) => {
        const imageElement = $img[0]
        if (!(imageElement instanceof HTMLImageElement)) {
          throw new Error('Expected collapsed preview image element')
        }
        if (!imageElement.complete) {
          throw new Error('Collapsed preview image is not loaded yet')
        }
        const contentElement = imageElement.closest('.note-content')
        if (!(contentElement instanceof HTMLElement)) {
          throw new Error('Expected note-content container for collapsed preview image')
        }

        const imageRect = imageElement.getBoundingClientRect()
        const contentRect = contentElement.getBoundingClientRect()

        expect(imageRect.width).to.be.greaterThan(0)
        expect(imageRect.width).to.be.lessThan(180)
        expect(imageRect.height).to.be.greaterThan(0)
        expect(imageRect.height).to.be.greaterThan(30)
        expect(imageRect.height).to.be.lessThan(120)
        expect(imageRect.width).to.be.lessThan(contentRect.width * 0.9)
      })
    })
  })
})
