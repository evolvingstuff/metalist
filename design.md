# MetaList Design Document

## Core Data Model

### Notes
- `id`: UUID string (primary key)
- `content`: String (note content)
- `parent_id`: UUID string (foreign key to notes)
- `position`: String (fractional index for ordering)
- `version`: Integer (for versioning)
- `content_hash`: String (for change detection)

### Ordering System (Fractional Indexing)
- Uses lexicographic string ordering for note positions
- Position examples: 'a', 'b', 'b5', 'c'
- Never needs rebalancing
- Supports infinite insertions between any two positions
- Efficient for filtered views and partial loading

### Version Control
- Each note has a version number
- Version increments on content or structural changes
- Content hash tracks both content and position changes
- Enables conflict detection and resolution

## API Design

### Endpoints
1. Note Management
   - `POST /notes/new`: Create new note
   - `PUT /notes/{id}`: Update note content
   - `POST /notes/{id}/move`: Move note (using fractional indexing)
   - `DELETE /notes/{id}`: Delete note and descendants

2. Version Control
   - `GET /notes/version`: Get current version
   - `POST /notes/undo`: Undo last action
   - `POST /notes/redo`: Redo last undone action

### Response Format
```json
{
  "version": 123,
  "changes": {
    "added": [{
      "id": "uuid",
      "content": "text",
      "parent_id": "parent-uuid",
      "position": "b5",
      "version": 123,
      "content_hash": "hash"
    }],
    "updated": [...],
    "deleted": [...]
  }
}
```

## Frontend Design

### Note Rendering
- Hierarchical structure based on parent_id
- Ordering based on lexicographic position strings
- Support for filtered views while maintaining order

### User Interactions
- Drag and drop using position strings
- Real-time updates with version tracking
- Conflict resolution UI

## Performance Considerations

### Scalability
- System designed to handle 100k+ notes
- Efficient position calculation without rebalancing
- Indexed queries on parent_id and position

### Search and Filtering
- Maintains correct ordering in filtered views
- Position-based insertion for filtered results
- Efficient partial loading support
