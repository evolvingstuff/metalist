const { defineConfig } = require('cypress')

module.exports = defineConfig({
  e2e: {
    baseUrl: 'http://localhost:8000',
    viewportWidth: 1280,
    viewportHeight: 720,
    video: false,
    screenshotOnRunFailure: true,
    defaultCommandTimeout: 5000,
    specPattern: 'cypress/e2e/**/*.cy.{js,jsx,ts,tsx}',
    failOnStatusCode: false
  },
})