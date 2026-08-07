# Deferred Security Work

## Status

MetaList's current security posture is considered sufficient for its intended
deployment: a personal, single-user application running on trusted computers
and accessed over a trusted home or work LAN. The items below are intentionally
deferred. They are not known emergency vulnerabilities and do not block normal
use or release.

The primary security objective is protecting the confidentiality of encrypted
user data. Availability-only threats, including deletion and service
disruption, are a lower priority for this deployment model.

## Revisit First: Software Supply Chain and Releases

A malicious dependency or compromised MetaList release could execute inside the
server process while a namespace is unlocked. At that point it could access the
in-memory data-encryption key and decrypted data, bypassing storage encryption,
authentication, CSP, and request-boundary protections.

MetaList already pins direct Python dependencies, records transitive artifacts
and hashes in `uv.lock`, publishes through PyPI Trusted Publishing, and updates
only when the user explicitly requests an update. Future hardening could add:

- A CI gate that runs the complete Python and JavaScript test suites, startup
  sanity checks, and a known-vulnerability dependency audit.
- A requirement that the CI security gate pass before a PyPI release job can
  publish.
- Tests against the built wheel and source distribution, rather than testing
  only the source checkout.
- Inspection of the built distributions to ensure that they contain only the
  intended files.
- Immutable commit-SHA pins for third-party GitHub Actions instead of movable
  version tags.
- Periodic review of direct and transitive dependencies, especially packages
  that parse HTML, images, multipart uploads, archives, or cryptographic data.

## Periodic Verification

These are maintenance exercises rather than new application features:

- Perform an occasional full security review after substantial authentication,
  encryption, networking, HTML-rendering, backup, restore, or update changes.
- Periodically run the encrypted-namespace storage audit and confirm that newly
  persisted fields have been added to its storage contract.
- Test restoring a real backup into a controlled environment so backup
  recoverability is demonstrated rather than assumed.
- Review persistent server logs and browser storage after new diagnostics or UI
  state features are introduced, ensuring that decrypted note text, searches,
  passwords, tokens, and keys are absent.
- Reassess TLS and certificate handling if MetaList moves beyond a trusted LAN,
  becomes internet-accessible, or is deployed behind a cloud service or reverse
  proxy.

## Deployment Changes That Require a New Threat Model

The present security conclusion should be revisited before any of the following:

- Hosting MetaList on the public internet or in a cloud environment.
- Supporting multiple users or users who do not fully trust one another.
- Allowing third-party plugins, extensions, automation, or agent access.
- Exposing `@shell` outside a loopback-only, explicitly enabled local workflow.
- Accepting databases, backup archives, or imports supplied by untrusted people.
- Running MetaList on an untrusted or shared operating-system account.
- Adding browser-accessible outbound network destinations beyond the current
  same-origin policy.

Such deployments would likely need stronger identity and authorization models,
managed TLS, secrets management, tenant isolation, audit logging, deployment
sandboxing, and a separate design for any shell-like capability.

## Known Residual Risks

The following cannot be fully solved by additional MetaList application code:

- Malware, an administrator, or another sufficiently privileged process on the
  host can inspect process memory, control the browser, or modify executable
  code while a namespace is unlocked.
- A browser extension with permission to read or modify MetaList pages can see
  decrypted data rendered in the page.
- Process-memory inspection may recover the in-memory data-encryption key or
  decrypted content during an authenticated session.
- A user who proceeds through an unexpected TLS certificate warning may connect
  to an impersonating server.
- A compromised build, release account, dependency, or package repository could
  deliver code that reads decrypted data at runtime.

Operational mitigations include using a trusted and patched computer, limiting
browser extensions, treating unexpected certificate changes as suspicious,
locking MetaList when it is not in use, and installing releases only from the
expected project.

## Low-Priority or Excessive Controls for the Current Deployment

Unless the threat model changes, the following are not currently justified by
their complexity or inconvenience:

- Client TLS certificates for ordinary LAN access.
- Hardware security module integration.
- Routine data-encryption-key rotation without evidence of key compromise.
- More expensive Argon2id settings solely for marginal gains over the current
  memory-hard configuration and password policy.
- Eliminating all in-memory plaintext while the user is actively viewing or
  editing notes.
- Enterprise multi-user authorization, tenant isolation, or centralized audit
  infrastructure.

## Decision

No further security feature is presently required for the personal trusted-LAN
deployment. Future work should begin with supply-chain and release verification,
or with a fresh threat-model review if the deployment assumptions change.
