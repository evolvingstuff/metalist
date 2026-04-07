# MetaList Backup Plan (Google Drive First)

## Purpose

This document describes a practical, implementation-oriented plan for adding cloud backups to MetaList, starting with **Google Drive only**.

The goal is to ship a backup feature that feels simple for nontechnical users:

- connect Google Drive
- choose whether backups run automatically
- let MetaList store backup snapshots in a visible Drive folder
- restore from a list of prior backups

This plan intentionally avoids solving "all cloud providers" in v1. It focuses on the smallest product and architecture that is both:

- **pleasant for ordinary users**, and
- **cleanly extensible later** if MetaList adds S3, Azure Blob, OneDrive, Dropbox, etc.

---

# 1. Product Positioning

## 1.1 What this feature is

This feature is **backup**, not sync.

That means:

- backups are point-in-time snapshots
- backups are one-way writes from MetaList to Drive
- restoring is an explicit user action
- backup artifacts are immutable once written
- users can have multiple restore points over time

## 1.2 What this feature is not

This feature is not:

- live bidirectional sync
- collaborative multi-device merge
- note-by-note export browsing
- cloud-native storage of the live workspace DBs

Keeping this distinction sharp matters for both UX and implementation.

---

# 2. Storage Reality in MetaList

## 2.1 Backup unit

A MetaList namespace is stored as a set of sibling SQLite databases:

- `~/MetaList/namespaces/<ns>/<ns>.metalist.db`
- `~/MetaList/namespaces/<ns>/<ns>.metalist.files.db`
- `~/MetaList/namespaces/<ns>/<ns>.metalist.search-history.db`

Launch/port settings for namespaces are tracked separately in:

- `~/MetaList/namespaces.db`

For backups, the operational unit should be the **namespace snapshot**, not any individual DB.

## 2.2 Consequence

A valid backup for one namespace must include all DBs that define that workspace together.

For v1, the restore unit should be:

- one namespace
- one snapshot archive

The system should refuse partial restore of only one DB file from a namespace backup.

---

# 3. Scope for V1

## 3.1 In scope

- Google Drive connection via OAuth
- one visible backup folder in the user's Drive
- manual backup for a namespace
- scheduled automatic backups for a namespace
- retention policy based on count (for example keep last 30)
- restore from a previous backup
- status display: last success, next run, latest error
- namespace-scoped configuration

## 3.2 Out of scope

- AWS S3
- Azure Blob
- Dropbox / OneDrive
- incremental or deduplicated backups
- selective restore of attachments vs notes DB
- cross-namespace bundled backups
- shared-drive support
- end-to-end encryption before upload (optional future phase)
- background multi-device sync
- conflict resolution across devices

## 3.3 Why this scope is right

Google Drive gives the best mainstream UX for nontechnical users because it supports a familiar account connection flow and visible folder-based storage.

Everything else can come later as an advanced target once the backup product shape is stable.

---

# 4. User Experience Goals

## 4.1 Core UX principle

The feature should feel like:

> Save backups of this workspace to my Google Drive.

It should not feel like:

> Configure a cloud storage provider with credentials, scopes, buckets, and prefixes.

## 4.2 User story

A nontechnical user should be able to:

1. open Backups settings for a namespace
2. click **Connect Google Drive**
3. sign in and approve access
4. see that MetaList will store backups in a clear Drive folder
5. turn on automatic backups
6. choose a schedule and retention count
7. click **Back up now** or let scheduled backups run
8. later restore from a list of dated backups

## 4.3 UX defaults

Recommended defaults:

- destination folder: `MetaList Backups/<namespace>/`
- automatic backups: enabled after initial setup
- schedule: daily
- retention: keep last 30 backups
- first backup: run immediately after setup

These defaults should be opinionated so the user can finish setup quickly without needing to understand storage details.

---

# 5. User Flows

## 5.1 First-time setup flow

### Entry point

A namespace settings page should include a **Backups** section.

Suggested CTA:

- **Back up this workspace**

### Flow

1. User opens the Backups section for namespace `default`
2. MetaList shows a simple explanation:
   - backups are saved to Google Drive
   - backups include the full workspace snapshot for this namespace
3. User clicks **Connect Google Drive**
4. Browser enters Google OAuth flow
5. On success, MetaList creates or locates:
   - `MetaList Backups/default/`
6. MetaList shows a confirmation screen:
   - destination folder
   - automatic backups toggle
   - frequency
   - retention
7. User clicks **Finish setup**
8. MetaList optionally runs first backup immediately

## 5.2 Manual backup flow

1. User opens Backups page
2. User sees status and existing backups
3. User clicks **Back up now**
4. UI shows progress stages:
   - preparing snapshot
   - compressing backup
   - uploading to Google Drive
   - finished
5. UI updates last successful backup timestamp

## 5.3 Scheduled backup flow

1. MetaList background scheduler sees a namespace is due
2. It creates a namespace snapshot
3. It uploads to Drive
4. It deletes older backups beyond retention count
5. UI shows updated last success / next scheduled time

## 5.4 Restore flow

1. User opens Backups page
2. User sees dated restore points
3. User clicks **Restore** on a specific backup
4. MetaList warns:
   - restore will create a new namespace by default, or
   - overwrite existing namespace only after explicit confirmation
5. MetaList downloads archive
6. MetaList verifies manifest and checksums
7. MetaList restores into:
   - preferred default: a new namespace, e.g. `default-restored-2026-04-06`
8. UI reports completion and offers switch-to-namespace action

## 5.5 Reconnect flow

When tokens expire or are revoked:

1. Backup run fails with an auth-related error
2. UI shows **Reconnect Google Drive**
3. User re-runs OAuth flow
4. Existing backup config remains intact
5. Scheduled jobs resume once connection is valid again

---

# 6. UX Details and UI Recommendations

## 6.1 Backups page layout

Suggested sections:

### A. Status card

Show:

- Destination: Google Drive
- Folder: `MetaList Backups/<namespace>/`
- Automatic backups: on/off
- Last successful backup
- Next scheduled backup
- Last error, if any

### B. Actions

Buttons:

- **Back up now**
- **Reconnect Google Drive** (conditional)
- **Turn automatic backups on/off**
- **Restore from backup**

### C. Backup settings

Fields:

- frequency: daily / weekly
- retention count: 10 / 30 / 90 / custom
- optional: encrypt before upload (future)

### D. Backup history

A dated list showing:

- backup timestamp
- archive size
- status
- restore action
- delete action (optional)

## 6.2 Language to use

Use user-facing language like:

- "Google Drive"
- "Backup folder"
- "Back up now"
- "Automatic backups"
- "Restore point"
- "Reconnect"

Avoid exposing implementation terms such as:

- access token
- refresh token
- Drive file ID
- MIME type
- scope
- redirect URI

## 6.3 Error message policy

Collapse backend errors into a few understandable messages.

Examples:

- "Reconnect Google Drive to continue backups."
- "Your Google Drive appears to be out of storage."
- "Backup failed. Please try again."
- "Restore failed because the backup file could not be verified."

Store detailed technical diagnostics in logs, not the main user-facing error surface.

---

# 7. Google Drive Product Choices

## 7.1 Visible folder vs hidden app data

MetaList should use a **visible Drive folder**, not a hidden app data area.

Why:

- backups are safety artifacts users may want to see
- visible files improve trust
- visible folders make support easier
- users understand folder-based ownership better than hidden app storage

## 7.2 Folder strategy

For v1, MetaList should automatically create a top-level backup folder if needed:

- `MetaList Backups/`

Within it, create one folder per namespace:

- `MetaList Backups/default/`
- `MetaList Backups/work/`
- `MetaList Backups/research/`

This gives a predictable structure and avoids forcing a folder picker into the first release.

## 7.3 Folder selection in v1

Recommendation: **do not ship custom folder picking in v1**.

Reason:

- it adds UI and permission complexity
- it is not needed for a good initial experience
- app-created folders are enough to validate the product

Custom folder selection can come later if user demand appears.

## 7.4 Naming of backup artifacts

Recommended archive naming:

- `<namespace>-YYYYMMDD-HHMMSS.metalist-backup.zip`

Example:

- `default-20260406-184200.metalist-backup.zip`

Advantages:

- readable in Drive UI
- sortable by name
- namespace obvious at a glance
- format future-proof enough for support tooling

---

# 8. Backup Artifact Format

## 8.1 Artifact shape

Each backup should be a single archive file uploaded to Drive.

Recommended contents:

- namespace snapshot copy of main DB
- namespace snapshot copy of files DB
- namespace snapshot copy of search-history DB
- manifest JSON

Suggested layout inside the archive:

```text
manifest.json
namespace/<ns>.metalist.db
namespace/<ns>.metalist.files.db
namespace/<ns>.metalist.search-history.db
```

## 8.2 Why a single archive

A single archive is the correct default because:

- upload semantics are simpler
- retention is simpler
- restore is simpler
- user sees one file per restore point
- provider differences matter less

## 8.3 Manifest contents

Manifest should include at least:

- backup format version
- app name
- app version
- namespace
- timestamp
- file names
- byte counts
- per-file SHA-256 hashes
- archive creation metadata

Suggested example:

```json
{
  "backup_format": 1,
  "app": "MetaList",
  "app_version": "0.1.0",
  "namespace": "default",
  "created_at": "2026-04-06T18:42:00Z",
  "files": [
    {
      "name": "default.metalist.db",
      "bytes": 123456,
      "sha256": "..."
    },
    {
      "name": "default.metalist.files.db",
      "bytes": 456789,
      "sha256": "..."
    },
    {
      "name": "default.metalist.search-history.db",
      "bytes": 34567,
      "sha256": "..."
    }
  ]
}
```

## 8.4 Compression choice

Recommended default: ZIP.

Why:

- universally understood
- easy to inspect
- easy to implement in Python
- sufficient for v1

Alternative formats such as tar+zstd can be considered later if compression ratio or performance becomes a real issue.

---

# 9. Consistent SQLite Snapshot Strategy

## 9.1 Requirement

MetaList must not create backups by naively copying live DB files while they may be actively written.

The backup process must create **transactionally consistent snapshot copies** of each SQLite database first.

## 9.2 Recommended method

Use Python's SQLite backup API:

- `sqlite3.Connection.backup(...)`

For each DB:

1. open source DB read-only
2. open destination temp DB
3. invoke SQLite backup API
4. close both
5. hash the copied DB

## 9.3 Process outline

For namespace `<ns>`:

1. create a temp working directory
2. snapshot `<ns>.metalist.db`
3. snapshot `<ns>.metalist.files.db`
4. snapshot `<ns>.metalist.search-history.db`
5. generate manifest
6. write ZIP archive
7. upload archive to Drive
8. verify upload success
9. delete temp working files

## 9.4 Why snapshot first

This cleanly separates:

- correctness of local data capture
- packaging into archive
- remote upload to Drive

That separation will matter later if other backup targets are added.

---

# 10. Architecture Overview

## 10.1 Main principle

Even though v1 only supports Google Drive, MetaList should still separate:

- backup snapshot generation
- backup artifact packaging
- remote destination integration

This keeps the design coherent without prematurely over-engineering for multiple providers.

## 10.2 Suggested components

### A. `NamespaceSnapshotService`

Responsible for:

- locating namespace DB files
- producing consistent snapshot copies
- hashing snapshot copies
- writing manifest

### B. `BackupArchiveService`

Responsible for:

- creating archive names
- writing ZIP files
- optionally validating contents before upload

### C. `GoogleDriveBackupService`

Responsible for:

- ensuring backup folder exists
- uploading archive
- listing archives
- downloading archive
- deleting old archives
- validating connection

### D. `BackupCoordinator`

Responsible for:

- orchestrating manual backup runs
- orchestrating scheduled backup runs
- invoking retention cleanup
- recording job history / status

### E. `RestoreService`

Responsible for:

- downloading archive
- verifying manifest and hashes
- restoring into target namespace
- protecting against destructive overwrite mistakes

## 10.3 Why not build a generic provider framework now

V1 does not need a complete provider plugin system. It only needs clean internal boundaries.

That means you should avoid building a giant abstraction tree before validating the product.

However, you should keep the Google Drive logic isolated enough that a future provider could later implement the same high-level operations:

- put artifact
- list artifacts
- get artifact
- delete artifact
- validate connection

---

# 11. Data Model Additions

## 11.1 New tables / records needed

MetaList should store backup configuration and state separately from the namespace contents being backed up.

Suggested records:

### A. Backup connection

Stores the Google account connection record.

Fields:

- `id`
- `provider` = `google_drive`
- `display_name`
- `google_account_email` (if available)
- `secret_ref` for token storage
- `created_at`
- `updated_at`
- `last_validated_at`
- `status` (`connected`, `needs_reconnect`, `invalid`)

### B. Namespace backup settings

Fields:

- `namespace`
- `connection_id`
- `enabled`
- `schedule_kind` (`daily`, `weekly`, etc.)
- `schedule_time`
- `retention_count`
- `drive_folder_id`
- `drive_folder_path_display`
- `last_success_at`
- `last_failure_at`
- `last_error_code`
- `last_error_message`
- `next_run_at`

### C. Backup job history

Fields:

- `id`
- `namespace`
- `started_at`
- `finished_at`
- `status` (`running`, `success`, `failed`)
- `archive_name`
- `archive_bytes`
- `remote_file_id`
- `manifest_json`
- `error_code`
- `error_message`

## 11.2 Secret storage

Do not store raw Google OAuth access/refresh tokens in plain config rows.

Use one of:

- OS keychain / secure credential storage
- encrypted secrets table
- another local secret abstraction that is clearly separated from ordinary app settings

This is especially important because refresh tokens are long-lived and effectively grant continued access.

---

# 12. Google OAuth Plan

## 12.1 Desired connection experience

The user should only see:

- Connect Google Drive
- choose account
- approve access
- return to MetaList

They should not need to understand OAuth terminology.

## 12.2 Connection workflow

1. User clicks **Connect Google Drive**
2. Backend starts OAuth flow and produces authorization URL
3. Browser is redirected to Google
4. User signs in and approves
5. Google redirects back to MetaList callback endpoint
6. Backend exchanges code for tokens
7. Tokens are stored securely
8. Backend verifies access by querying or creating the backup folder
9. Connection record is marked `connected`

## 12.3 Token lifecycle

The app should support:

- access token refresh using refresh token
- reconnect when refresh token is invalidated or revoked
- validation before important operations

## 12.4 First release constraint

V1 should target a straightforward OAuth path for a single-user/local app architecture.

Do not over-complicate v1 with multi-tenant enterprise Google account edge cases unless they are part of MetaList's target audience.

---

# 13. API Design (FastAPI)

## 13.1 Connection endpoints

Suggested endpoints:

### `POST /api/backups/google-drive/connect/start`

Returns:

- authorization URL
- state token or flow metadata

### `GET /api/backups/google-drive/connect/callback`

Handles Google redirect, stores tokens, creates/locates backup folders.

### `POST /api/backups/google-drive/validate`

Checks whether the saved connection is still valid.

### `POST /api/backups/google-drive/disconnect`

Disconnects Google Drive for MetaList backups.

## 13.2 Backup settings endpoints

### `GET /api/namespaces/{namespace}/backup-settings`

Returns current backup settings and status.

### `PUT /api/namespaces/{namespace}/backup-settings`

Updates:

- enabled
- schedule
- retention count
- destination folder display info

## 13.3 Backup operation endpoints

### `POST /api/namespaces/{namespace}/backups/run`

Starts an immediate backup for the namespace.

### `GET /api/namespaces/{namespace}/backups`

Lists known backup records and remote artifacts.

### `GET /api/namespaces/{namespace}/backups/history`

Returns job history and status.

### `POST /api/namespaces/{namespace}/backups/{backup_id}/restore`

Restores selected backup to:

- a new namespace, or
- overwrite existing namespace if explicitly requested

## 13.4 Internal vs external IDs

The API should expose MetaList backup IDs cleanly without leaking raw Drive implementation details unless needed.

Internally you may store Google Drive file IDs, but the frontend should not need them except as internal opaque references.

---

# 14. Google Drive Integration Details

## 14.1 Folder structure

Recommended structure in Drive:

```text
MetaList Backups/
  default/
    default-20260406-184200.metalist-backup.zip
    default-20260407-184200.metalist-backup.zip
  work/
    work-20260406-191500.metalist-backup.zip
```

## 14.2 Drive metadata to track locally

For each namespace settings record, store:

- top-level backup folder ID (optional)
- namespace folder ID
- namespace folder display path

For each backup job, store:

- remote Drive file ID
- remote file name
- upload time
- file size if available

## 14.3 Upload semantics

Upload should be treated as artifact creation.

Do not attempt to overwrite a previous archive in place.

Each backup should create a new file with a unique timestamped name.

This aligns with backup semantics and makes retention cleanup easy.

## 14.4 Listing semantics

When showing restore points:

- prefer local backup history if available
- reconcile with Drive listing when needed
- if local history is missing or stale, Drive can be treated as the source of discoverable backup artifacts

## 14.5 Deletion semantics

Retention cleanup should delete the oldest archives beyond the configured retention count for that namespace folder.

Deletion should be performed after a new backup is successfully uploaded, not before.

---

# 15. Scheduler / Background Execution

## 15.1 Requirement

Scheduled backups need a background execution mechanism.

## 15.2 Suggested approach

Use a simple internal scheduler appropriate to your app runtime model.

Core requirements:

- periodically scan enabled namespace backup settings
- identify jobs due to run
- ensure only one backup job per namespace runs at a time
- persist job status to storage
- survive app restarts reasonably well

## 15.3 Concurrency rules

Rules:

- one running backup per namespace at a time
- one running restore per target namespace at a time
- backups and restores should not stomp on the same namespace simultaneously

## 15.4 Locking

Introduce a namespace-level lock for backup/restore operations.

This can initially be a local process-level lock plus persisted job state.

If MetaList later supports true multi-process/multi-instance execution, this may need strengthening.

---

# 16. Restore Design

## 16.1 Default restore behavior

Default restore target should be a **new namespace**, not overwrite.

Reason:

- much safer for users
- easier to debug
- avoids accidental destruction
- allows quick comparison with current state

Suggested target naming:

- `<namespace>-restored-YYYYMMDD-HHMMSS`

## 16.2 Optional overwrite behavior

Overwrite restore can exist, but should require explicit confirmation and ideally the namespace should be inactive during the operation.

## 16.3 Restore steps

1. download archive from Drive
2. unzip to temp directory
3. read manifest
4. verify required files exist
5. verify SHA-256 hashes
6. create target namespace directory
7. place DB files in target namespace directory
8. register namespace if needed
9. report completion

## 16.4 Validation rules

Restore should fail if:

- manifest is missing
- required DB files are missing
- file hash mismatch occurs
- archive format version is unsupported
- target namespace already exists and overwrite not permitted

---

# 17. Retention Policy

## 17.1 V1 retention model

Use a simple count-based policy:

- keep last `N` successful backups per namespace

Recommended default:

- `N = 30`

## 17.2 When retention cleanup runs

Run cleanup only after a new backup succeeds.

This ensures a transient upload failure does not reduce the number of available restore points.

## 17.3 Failed jobs and retention

Failed backup jobs should not count toward retention.

Only successfully uploaded, verifiable backup artifacts should count.

---

# 18. Observability and Supportability

## 18.1 Logs

Log structured events for:

- OAuth connect start / finish
- token refresh attempts
- folder creation / lookup
- backup job start / finish
- archive creation duration
- upload duration
- retention deletion
- restore start / finish
- validation failures

## 18.2 Metrics to consider

Useful metrics:

- number of connected backup namespaces
- number of successful backups
- number of failed backups
- average backup archive size
- average upload duration
- number of reconnect-required states
- number of restores performed

## 18.3 User-visible diagnostics

The UI only needs small status summaries. The detailed cause should remain in logs for support/debugging.

---

# 19. Security Considerations

## 19.1 Local secrets

Google tokens must be stored securely.

## 19.2 Principle of least privilege

Request the narrowest Google Drive access that still supports the chosen UX.

Because v1 uses an app-controlled backup folder strategy, the permission model should be kept as limited as practical.

## 19.3 Backup confidentiality

V1 can ship without client-side encryption if needed, but this should be an explicit product decision.

Tradeoff:

- without encryption, backups are readable to anyone with access to the user's Drive account or local machine
- with encryption, recovery becomes more complex and key management must be handled carefully

Recommendation:

- make encryption a future phase unless it is a hard requirement now
- but design the archive pipeline so encryption can be inserted later between archive creation and upload

## 19.4 Restore safety

Prefer new-namespace restore by default to reduce accidental destructive actions.

---

# 20. Failure Modes to Plan For

## 20.1 OAuth revoked

Symptom:

- upload/list/download requests fail with auth error

Expected app behavior:

- mark connection as `needs_reconnect`
- show reconnect CTA
- do not spam repeated failing scheduled runs without backoff

## 20.2 Drive storage exhausted

Symptom:

- upload rejected by provider

Expected app behavior:

- report clear user-facing error
- retain existing backups
- do not delete older backups in same run

## 20.3 Local snapshot failure

Symptom:

- one or more SQLite snapshots cannot be created

Expected app behavior:

- fail the job before archive creation
- leave existing remote backups untouched

## 20.4 Archive corruption

Symptom:

- ZIP creation fails or checksum mismatch discovered later

Expected app behavior:

- fail job
- do not upload incomplete artifact
- log full diagnostics

## 20.5 Namespace locked or busy

Symptom:

- backup already running or restore in progress

Expected app behavior:

- show "backup already in progress" or queue behavior, depending on design

---

# 21. Development Plan

## Phase 0: groundwork

Goal:

- define backup data model and job records
- define namespace lock rules
- define archive format and manifest version

Deliverables:

- schema changes for backup settings/history
- archive naming and manifest schema finalized
- internal service boundaries decided

## Phase 1: local snapshot + archive creation

Goal:

- build correct namespace backup artifact locally without any cloud integration

Deliverables:

- snapshot service using SQLite backup API
- manifest generation
- ZIP archive generation
- archive verification helper

Acceptance checks:

- manual creation of archive for namespace succeeds
- archive contains all expected DBs
- hashes verify
- restore from local archive works into a new namespace

## Phase 2: Google OAuth connection

Goal:

- connect a Google account and securely persist tokens

Deliverables:

- connect start endpoint
- callback handler
- token persistence
- validate connection endpoint
- disconnect support

Acceptance checks:

- user can connect account
- app can verify connection
- app can create or find `MetaList Backups/` folder

## Phase 3: Drive upload/list/download/delete

Goal:

- treat Google Drive as an artifact destination

Deliverables:

- ensure namespace folder exists
- upload archive
- list namespace backups
- download archive by ID
- delete old archives for retention

Acceptance checks:

- a local archive can be uploaded
- uploaded archive appears in expected Drive folder
- listed backups appear in UI/API
- file can be downloaded and restored

## Phase 4: manual backup UX

Goal:

- full end-to-end user flow for connected Google Drive backup

Deliverables:

- Backups page for namespace
- status card
- manual backup button
- backup history list
- basic error display

Acceptance checks:

- user can set up backup and run first backup without technical knowledge
- UI clearly shows destination, last success, and errors

## Phase 5: scheduled backups + retention

Goal:

- automatic ongoing backups

Deliverables:

- scheduler
- due-job selection
- namespace locking
- retention cleanup after successful upload
- next-run calculation

Acceptance checks:

- daily and weekly schedules execute correctly
- only one backup runs per namespace at a time
- old backups are deleted after successful new uploads

## Phase 6: restore UX

Goal:

- make restore safe and understandable

Deliverables:

- restore action from backup history
- default restore-to-new-namespace path
- overwrite option with explicit confirmation
- restore status display

Acceptance checks:

- user can restore from a listed backup to a new namespace
- restored namespace opens successfully in MetaList

## Phase 7: polish and resilience

Goal:

- make failures understandable and supportable

Deliverables:

- reconnect flows
- better error mapping
- structured logs
- job retry/backoff policy
- support tooling / diagnostics improvements

Acceptance checks:

- revoked token is handled cleanly
- failed jobs do not destroy retention state
- logs clearly show step of failure

---

# 22. Suggested Internal Python Module Layout

```text
metalist/
  backups/
    __init__.py
    models.py
    manifest.py
    archive.py
    snapshot.py
    coordinator.py
    retention.py
    restore.py
    scheduler.py
    locks.py
    google_drive.py
    oauth_google.py
    api.py
```

## Module responsibilities

### `snapshot.py`

- resolve namespace paths
- snapshot SQLite DBs
- compute hashes

### `manifest.py`

- define manifest schema
- serialize / parse manifest
- verify hashes

### `archive.py`

- build ZIP archive
- unpack archive

### `google_drive.py`

- folder lookup/creation
- upload/download/list/delete
- provider-specific error mapping

### `oauth_google.py`

- start OAuth flow
- exchange code for tokens
- refresh tokens
- validate connection

### `coordinator.py`

- manual backup orchestration
- scheduled backup orchestration
- status writes

### `restore.py`

- restore orchestration
- target namespace checks

### `retention.py`

- list existing backups
- compute excess backups
- delete excess backups

### `scheduler.py`

- periodic due-job runner

### `locks.py`

- namespace-level operation guards

### `api.py`

- FastAPI routes

---

# 23. Testing Plan

## 23.1 Unit tests

Test:

- manifest generation/parsing
- hash verification
- archive build/unpack
- schedule next-run calculation
- retention computation
- namespace lock behavior

## 23.2 Integration tests

Test:

- snapshot of sample namespace DB set
- local restore to new namespace
- backup history persistence
- retry behavior after simulated failures

## 23.3 Provider integration tests

Test with a real or test Google Drive setup:

- connect flow
- folder creation
- file upload
- file listing
- file download
- file deletion

## 23.4 Manual QA scenarios

Scenarios:

- first-time setup on empty namespace
- backup of large namespace with attachments
- revoke Google access and verify reconnect UX
- fill Drive quota / simulate storage failure
- restore into new namespace and compare content
- scheduled backup after app restart

---

# 24. Open Questions

These should be resolved before implementation or during early development:

1. Should backup settings live in `namespaces.db` or in a new global MetaList settings DB?
2. What local secret storage mechanism is preferred on each supported platform?
3. Does MetaList already have a background job framework, or does backup scheduling need its own?
4. Should backup archives include any namespace-level config beyond the three SQLite DBs?
5. Should the app automatically pause backup jobs if repeated auth failures occur?
6. Does MetaList need backup notifications or only passive status display?
7. Is client-side encryption required for the initial release or explicitly deferred?
8. Should restore automatically register the new namespace in `namespaces.db`, or should that be a separate step?

---

# 25. Explicit Non-Goals for V1

To keep scope under control, v1 should not attempt to solve:

- generic multi-provider abstraction for all clouds
- live cloud sync of active workspace state
- per-note restore
- block-level incremental uploads
- deduplicated attachment backup
- collaborative backup sharing
- cross-account migration tooling
- mobile-first backup flows

---

# 26. Recommended First Implementation Sequence

If development begins immediately, the most effective sequence is:

1. implement local namespace snapshot and archive creation
2. implement local restore from archive
3. add backup settings schema and job history schema
4. implement Google OAuth connection flow
5. implement Drive folder creation and archive upload
6. implement manual backup end-to-end UI
7. implement list/download/restore UI
8. implement scheduler and retention
9. polish reconnect/error cases

This sequence forces correctness before cloud integration and cloud integration before scheduling complexity.

---

# 27. Final Recommendation

MetaList should start with a **Google-Drive-only backup feature** built around a **namespace snapshot archive** uploaded into a **visible Drive folder**.

This is the best first version because it:

- matches how ordinary users think
- avoids cloud-provider UX fragmentation
- keeps implementation bounded
- preserves room for future provider expansion
- aligns with MetaList's namespace-scoped SQLite storage model

The most important architectural rule is:

> keep snapshot creation, archive creation, and Drive upload as separate concerns.

That separation is the difference between a clean backup system and a feature that becomes hard to maintain as soon as new destinations are added.
