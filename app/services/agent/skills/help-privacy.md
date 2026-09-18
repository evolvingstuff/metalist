# MetaList privacy and security controls

Cloud AI privacy opens the privacy section of AI agent settings. Four fields,
one entry per line, configure whitelist tags/phrases and blacklist tags/phrases.
The policy is namespace-scoped. Whitelist entries use OR, blacklist entries use
OR, and a blacklist match wins. Effective tag matching includes inheritance and
ontology relationships; text phrases are case-insensitive literal phrases.
A hidden ancestor hides its descendants. Password-tagged notes always hide the
entire subtree from the AI. Filtering happens before note content, counts,
evidence, citations, debug, or provider requests. Hovering the chat column
previews excluded notes with readable gray backgrounds. It is not deletion.
A general product-help question does not need to send saved-note contents.

OpenAI credentials persist encrypted when the namespace is password-protected.
For a plaintext namespace they are held only in server session memory. Do not
ask the user to paste an API key or password into chat: open AI agent settings
or the appropriate password form. OpenAI requests use store:false; do not claim
this guarantees zero provider retention or overrides the provider's policies.

## Encryption at rest: scope and limits

Answer storage questions directly from these established facts. Do not describe
known implementation behavior as "the references do not establish it." Distinguish
what MetaList does from the user's actual current configuration, which this skill
does not inspect. For "is everything encrypted at rest?", explain both the broad
sensitive-data coverage and the specific exceptions; do not simply say yes or
give a vague disclaimer about protected content.

With namespace password protection enabled, MetaList uses AES-256-GCM for its
persisted sensitive payloads. This is application field-level encryption, not
whole-file SQLite encryption or OS full-disk encryption. Coverage includes:

- Note bodies, accepted tags and pending proposed tags; ontology rule text.
- Attachments in the sibling files database: file title, filename/MIME/other
  metadata, and file bytes. Embedded-document payloads are encrypted too.
- Saved tab state (including saved search state), aggregate tag-activity payloads,
  reminders, and cached link URLs/titles.
- UI/client preferences, command-palette usage/query tokens, backup settings,
  prompt/skill overrides and cloud privacy settings stored in client preferences.
- Persisted OpenAI credentials, when present in a protected namespace.

Readable structural/operational metadata remains: note IDs, parent/previous/next
relationships (hierarchy and order), collapse state, created/updated timestamps,
namespace names and listener ports, schema/vault versions, salts/KDF parameters,
the password verifier, ciphertext lengths and encryption nonces/tags. The DEK is
stored wrapped (encrypted), not as a readable raw key. Attachment filenames and
their metadata payload are encrypted; do not confuse them with readable database
structure or file/container sizes. Encryption does not hide all sizes or access
patterns. Machine-level network configuration also remains plaintext.

Without a namespace password, MetaList stores ordinary note and attachment
payloads in plaintext. This is known behavior, not merely an absence of a promise.
OS disk encryption is a separate layer and must not be assumed. An unprotected
namespace's OpenAI key is session-memory-only, not a persisted plaintext key.

Adding a password encrypts existing live sensitive data and subsequent writes.
Removing the password decrypts the live data. Changing the password rewraps the
same random 256-bit Data Encryption Key with a new password-derived key rather
than re-encrypting every note. Argon2id derives the password keys; authentication
verification and DEK wrapping use separate salts. The unwrapped DEK exists in
server memory while unlocked. No model/tool here can inspect or recover it.

## Backups and older copies

A backup copies consistent notes/files SQLite snapshots into a `.tar.gz` archive.
It does not decrypt encrypted payloads or add whole-archive encryption. A snapshot
of an encrypted namespace retains its encrypted sensitive payloads and wrapped
DEK; a snapshot of a plaintext namespace retains plaintext. The archive manifest
(namespace, creation time, file entries/checksums, encryption-enabled flag) and
structural metadata are readable. Thus "protected backup contents remain
encrypted" is correct; "every byte of every backup is encrypted" is not.

Existing backup files are immutable. Adding a password does not encrypt old
plaintext backups. Changing the live password does not change the password
needed for an older encrypted snapshot. Restore uses that snapshot's password,
leaves its source archive unchanged, and migrates only the installed live copy.
Encryption cannot retroactively protect exported HTML, downloaded files,
clipboard copies, older backups, OS snapshots or other copies outside the live
protected stores. Do not claim secure erasure of every historical disk byte.

Password creation/removal and restore use temporary live recovery images. During
password creation, the rollback image can retain the prior plaintext state until
successful commit/cleanup. It is distinct from historical backups. Do not advise
deleting recovery artifacts to bypass a failed transition.

## Diagnostics, memory and verification

For a protected namespace, startup diagnostics before unlock are plaintext and
do not contain decrypted vault data. After successful key unwrap, persistent
Loguru records and direct stdout/stderr writes use individual `MLLOG1` AES-GCM
envelopes with a DEK-derived logging key. Plaintext fault logging is disabled
during the unlocked interval. Do not claim logs are all always plaintext or all
always encrypted.

At-rest encryption does not protect decrypted content displayed in the browser
or decrypted data/keys in unlocked server memory from a privileged process or
browser extension. Explicit logout purges application-owned key and plaintext
store references. Idle timeout instead invalidates browser authentication while
keeping the hydrated server cache warm for re-login. These are different, and
neither is a guarantee of forensic zeroization of Python allocations/OS memory.

The startup encrypted-storage audit checks declared sensitive payload encryption
metadata, known table/column coverage, nonce uniqueness and SQLite integrity in
live namespace databases. Unsupported/unprotected current-version storage fails
loudly; known old-version issues may require authenticated migration. This is a
storage-contract check, not proof of every disk byte being encrypted or a scan
of all logs/backups/swap. It does not authenticate ciphertext without the key.

The Add password, Change password, and Remove password menus open forms. Opening
is not submitting. An encryption explanation alone does not request a form or a
password change. Never ask for an actual password or API key in chat.

Session idle timeout controls inactivity before reauthentication and can be
disabled. Explicit logout clears session AI state. The random password
generator is a local dialog; do not invent or expose actual saved passwords.

@password is a special view-only blurred, copyable credential field and an AI
exclusion boundary; @username is a copyable username field. A blurred display is
not a substitute for namespace encryption. @password's AI exclusion cannot be
bypassed by a cloud whitelist. @shell execution is separately opt-in on the server
(--enable-shell); AI help has no shell execution tool. Explain only what this
reference establishes; do not assert the user's current encryption, disclosure
policy, or session settings without explicit supplied evidence.

Maintainer sources: `app/encryption_audit.py` (payload/schema inventory),
`app/services/encryption.py`, `auth_service.py`, `password_note_fields.py`,
`file_storage.py`, `backup_service.py`, and `docs/security/README.md` plus
`docs/security/recovery.md`. These paths explain provenance, not additional
tools or permission to read a user's data.
