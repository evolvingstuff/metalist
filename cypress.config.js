const { defineConfig } = require('cypress')

module.exports = defineConfig({
  e2e: {
    baseUrl: 'http://localhost:5000',
    viewportWidth: 1280,
    viewportHeight: 720,
    video: false,  // Disable video recording for now
    screenshotOnRunFailure: true,
    defaultCommandTimeout: 5000,  // 5 seconds should be enough for our app
    setupNodeEvents(on, config) {
      // We can add custom plugins here later if needed
    },
  },
}) 