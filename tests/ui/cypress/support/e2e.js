// Import commands.js using ES2015 syntax:
import './commands'

// This is a good place to put global before/after hooks
beforeEach(() => {
  // Reset any state before each test
  cy.visit('/')
}) 