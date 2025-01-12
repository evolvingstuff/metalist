const { defineConfig } = require('cypress')

module.exports = defineConfig({
  e2e: {
    setupNodeEvents(on, config) {
      // Before all tests
      on('before:run', async () => {
        console.log('Setting up test environment...')
        
        return cy.request({
          method: 'POST',
          url: 'http://localhost:8000/dev/use-dev-db',
          failOnStatusCode: true,
          retries: 2
        }).then(() => {
          console.log('Successfully switched to dev database')
        }).catch(err => {
          throw new Error('Failed to switch to dev database:', err)
        })
      })

      // After all tests
      on('after:run', async () => {
        console.log('Switching back to production database...')
        
        return cy.request({
          method: 'POST',
          url: 'http://localhost:8000/dev/use-file-db',
          failOnStatusCode: true
        }).then(() => {
          console.log('Successfully switched back to production database')
        }).catch(err => {
          throw new Error('Failed to switch back to production database:', err)
        })
      })
    },
    baseUrl: 'http://localhost:8000'
  }
}) 