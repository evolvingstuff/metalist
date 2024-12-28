// Import commands.js using ES2015 syntax:
import './commands'

// This is a good place to put global before/after hooks
beforeEach(() => {
  // Switch to in-memory database before each test
  cy.request('POST', '/api/dev/use-memory-db').then((response) => {
    expect(response.status).to.eq(200)
    expect(response.body.status).to.eq('ok')
  })
  cy.visit('/')
})

after(() => {
  // Switch back to file database after all tests complete
  cy.request('POST', '/api/dev/use-file-db').then((response) => {
    expect(response.status).to.eq(200)
    expect(response.body.status).to.eq('ok')
  })
}) 