# Recovery runbook

This runbook covers the current live-database recovery protocol. It never repairs or migrates a historical backup in place. See [security architecture](README.md#recovery-of-live-database-changes) and [the test map](../testing/coverage-map.md).

## Interrupted password change or restore

Password creation/removal and multi-database restore have a durable recovery boundary. A checksummed `.<database-name>.recovery` directory beside the live namespace database contains temporary transaction images for the notes and files databases. It is live transaction state, separate from the `backups/` directory. A commit marker distinguishes committed work from work that must roll back. The empty `.recovery.lock` file can legitimately remain after cleanup.

1. If the request failed, stop retrying edits while the server is in maintenance mode. Record the error and namespace name; do not publish logs containing private data.
2. Resolve the reported external problem, such as a full disk or lost access to the live data directory. Do not delete recovery files to bypass a failure. Do not change permissions or timestamps on backup archives.
3. Restart the affected namespace normally. Startup attempts recovery before storage auditing or migrations. An interrupted operation without a durable commit marker restores its previous database pair; completed work retains the committed pair. Recovery can retry after another interruption.
4. Log in and verify representative notes, hierarchy, attachments, and settings. A transition rolled back before commit requires the previous password. An archive restore uses the password that protected the selected backup, which may differ from the former live namespace password.
5. If recovery still fails, retain the complete live transaction state and source backups for diagnosis. Do not remove tables, discard a sidecar, hand-edit a recovery manifest, or suppress `BKP001`/storage audit failures. The server intentionally stays unavailable rather than serving inconsistent state.

A live password transition may temporarily retain its previous plaintext state in the owner-only recovery directory until commit/cleanup. Existing archives are never rewritten to match a new password.

## Restore from an archive

Use MetaList's backup/restore UI for a validated archive or supported legacy backup. The application verifies the source, stages and checks the database pair, installs the live copies within the recovery boundary, and verifies the original source hashes again. A current-namespace restore restarts the server; log in again afterward. Session undo history is not a substitute for a backup and is cleared during session replacement/restore.

- Keep the original archive and any legacy sidecars together and byte-for-byte unchanged. Do not repackage an archive to fix a manifest, rename its contents, run SQLite migration commands on it, or overwrite it with a newly generated archive.
- Older plaintext databases migrate only after installation as live data. Older encrypted databases migrate after successful unlock. A newer unsupported database version requires a compatible application version; editing its version number is unsafe.
- A checksum mismatch, malformed archive, unsupported hierarchy, missing companion database, or invalid encryption metadata requires diagnosis or a different verified backup. Disabling checks is not recovery.
- Creating a new backup requires a distinct destination. Existing archive names cannot be overwritten. Retention/deletion is a separately authorized operation, not part of this runbook.

## Verify recovery in disposable storage

The safest routine exercise uses the automated browser smoke: it creates its own namespace, attachment and encrypted archive, restores it, verifies restart/reauthentication and checks that the source hash is unchanged.

```bash
npm run test:browser
```

To investigate a particular archive interactively, use a separate absolute data root and free listener ports. Configure `METALIST_DATA_DIRECTORY` **before** launching the application; do not change the environment of an already-running personal namespace. Use the UI to restore the selected source into that disposable instance. The source archive remains read-only to this workflow. Avoid hand-copying just a live `.db` while its writer is running: WAL and companion-file consistency matter.

The standalone storage audit reads live namespace databases and reports metadata/integrity problems. It does not recover a lost password, prove absence of every stale disk byte, or repair an archive. Use `metalist-audit-encryption --help` for its supported namespace-root option; never point mutation tooling at historical backup files.

## Release and platform limits

Local macOS tests cover injected storage errors, interrupted processes, rollback, actual browser restore/restart, and archive immutability. They do not simulate physical power loss or establish Windows/Linux behavior. Every release candidate still requires the exact-commit platform matrix described in [release controls](supply-chain.md#release-validation).

## Windows updater PE-resource failure

The September 19 report failed during uv's disposable candidate installation:
`Failed to update Windows PE resources: ...uv-trampoline.exe: Access is denied`.
The updater had not stopped live namespaces or changed the installed package.
This is separate from the preceding missing-tab-identity login failure, whose
original trigger remains unconfirmed. A denied file operation does not identify
which Windows component denied it.

`app/services/update_installer.py` selects a private, verified uv 0.12.17 when
Windows has uv older than 0.12.13. The official upstream change replaced temporary
PE-resource editing with in-memory editing. The same selected executable performs
both preflight and the final offline install. Cache files live under
`%LOCALAPPDATA%\MetaList\update-tools`, outside namespace backups. Archive and
executable SHA-256 values must match before execution; cached executables are
verified again on reuse. Download, verification, and version failures abort before
MetaList is stopped. See [installer provenance](supply-chain.md#windows-update-installer).

An old installed updater cannot gain this fix merely by publishing a new wheel.
Build a standalone repair ZIP with `.venv/bin/python scripts/build_windows_update_repair.py <new-output.zip>`.
After extraction, `Repair-MetaList.cmd` locates the existing tool's Python and runs
the same production installer-selection module. It prepends the verified uv only
to the child updater's PATH, then invokes the existing `metalist update`. Existing
preflight, backup, shutdown, installation, and restart behavior remain in charge.
It requires neither administrator privileges nor changes to security settings.

Validation: unit coverage checks installer selection, failure propagation,
checksum rejection, and the child environment. The required Windows/Python 3.13
CI leg installs the hash-pinned published 0.7.1 wheel (only its release-metadata URL
is redirected to the test index), extracts and runs the repair ZIP, verifies the
upgrade/backups/restarts, and exercises Chrome, Firefox, and Edge afterward. Each
browser covers ordinary encrypted login and deliberately removes the stored tab ID
after a successful login response to verify hydration still completes with the
original identity. Chrome over loopback HTTP matches the affected user's actual
browser and access route; Edge retains the additional certificate-verified LAN HTTPS
coverage. The corrected matrix has not run yet; the repair launcher must not be
presented as Windows-validated yet.

The first Windows Edge run reached password creation and exposed `OSError: [Errno
9] Bad file descriptor` while flushing a recovery image. `_sync_file` had opened
the owned file read-only; Windows' CRT rejects `fsync`/`_commit` on that descriptor.
It now opens the same existing file as `r+b`, which grants the required descriptor
access without truncating or changing its bytes. A regression forces the flush
through a writable-descriptor check. The complete Python and JavaScript suites and
startup gates now run symmetrically on all 15 OS/Python matrix legs; Edge and the
repair launcher remain additional Windows checks.
