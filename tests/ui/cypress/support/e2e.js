// Import commands.js using ES2015 syntax:
import './commands'

before(() => {
  cy.log('🔵 SUITE SETUP: Switching to dev database');
  return cy.request('POST', '/dev/use-dev-db')
    .then((response) => {
      expect(response.status).to.eq(200);
      cy.log('🔵 SUITE SETUP: Successfully switched to dev database');
    });
});

after(() => {
  cy.log('🔴 SUITE CLEANUP: Switching back to file database');
  return cy.request('POST', '/dev/use-file-db')
    .then((response) => {
      expect(response.status).to.eq(200);
      cy.log('🔴 SUITE CLEANUP: Successfully switched back to file database');
    });
}); 