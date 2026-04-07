function cacheBuster() {
  return `t=${Date.now()}`
}

Cypress.Commands.add('resetTestState', () => {
  cy.clearAllCookies({ log: false })
  cy.clearAllLocalStorage({ log: false })
  cy.clearAllSessionStorage({ log: false })
  return cy.request('POST', '/api2/test/reset')
    .its('body')
    .should('deep.equal', { ok: true })
})

Cypress.Commands.add('visitApp', (path) => {
  if (typeof path !== 'string') {
    throw new Error(`visitApp expects a string path, got ${typeof path}`)
  }
  const separator = path.includes('?') ? '&' : '?'
  cy.visit(`${path}${separator}${cacheBuster()}`, {
    onBeforeLoad(win) {
      win.localStorage.clear()
      win.sessionStorage.clear()
    },
  })
  cy.get('body', { timeout: 10000 }).should('not.have.class', 'loading')
  cy.get('body', { timeout: 10000 }).should('have.attr', 'data-app-ready', 'true')
  return cy.get('#search-input', { timeout: 10000 }).should('exist')
})
