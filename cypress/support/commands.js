function cacheBuster() {
  return `t=${Date.now()}`
}

Cypress.Commands.add('resetTestState', () => {
  cy.request('POST', '/api2/test/reset')
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
})
