# Sounds

Reusable sounds are namespace-local audio assets for in-app UI events.

## Storage

- DB: sibling `*.files.db`, table `sounds`.
- Runtime: `app/services/sound_storage.py:sound_store`.
- Pattern: memory-first after startup/login; SQLite is persistence only for normal runtime playback/listing.
- Encryption: metadata and blobs encrypt at rest when namespace password protection is enabled.
- Built-in: `builtin.default_chime` is always available, memory-backed, non-deletable, and not counted against uploaded usage.

## API

- `GET /api2/sounds`: list built-in + uploaded sounds and usage caps.
- `POST /api2/sounds/upload`: upload titled audio.
- `PUT /api2/sounds/{sound_id}`: rename uploaded sound.
- `DELETE /api2/sounds/{sound_id}`: delete uploaded sound unless selected by a reminder.
- `GET /api2/sounds/{sound_id}/play`: authenticated inline audio stream from memory.

## Limits

- Per sound: 2 MB.
- Duration: 10 seconds.
- Aggregate uploaded library: 50 MB per namespace.
- MIME allowlist: common browser-playable audio formats.
- Duration validation uses Python `mutagen` server-side.

## UI

- Command palette: `Manage sounds…`.
- Reminder modal: bottom default-sound controls plus per-reminder override dropdowns for popup sound and `Got it` sound.
- Per-reminder override dropdowns include `Silent` to explicitly suppress an otherwise audible default.
- Sound manager shows uploaded usage against the aggregate cap, supports upload, preview, rename, and delete.

## Deletion Rule

Uploaded sounds cannot be deleted while any reminder or reminder default references them for popup or `Got it` playback. Edit those selections to another sound first.
