# MetaList

A minimalist note-taking application with a focus on server-side rendering and efficient data synchronization.

## Features

- Rich text editing with image support
- Drag-and-drop note reordering
- Real-time content saving
- Keyboard shortcuts
- Server-side rendering for fast initial load
- Linked list data structure for efficient ordering

## Technology Stack

### Backend
- FastAPI - Modern Python web framework
- SQLAlchemy - SQL toolkit and ORM
- Mako - Server-side templating
- SQLite - Database storage

### Frontend
- Vanilla JavaScript (No framework)
- HTML5 Drag and Drop API
- ContentEditable for rich text editing
- CSS Custom Properties for theming

### Testing
- Cypress - End-to-end UI testing
- Property-based testing for backend

## Architecture

The application uses a server-side rendering approach with minimal JavaScript. Notes are stored in a linked list structure allowing for efficient reordering operations. Content synchronization is handled through a combination of immediate operations (drag-and-drop) and polled updates (content editing).

### Encrypted Single-User Design

MetaList is designed as a **single-user, encrypted-at-rest** application with the following principles:

- **In-Memory Operations**: All data is decrypted and loaded into memory at startup for optimal performance
- **Encryption-First**: Database stores only encrypted data; all processing happens on decrypted in-memory state
- **Container-Based Multi-User**: Multiple users supported via separate container instances
- **Crash-Safe**: Process crashes simply reload from encrypted storage; no persistent state corruption possible
- **Undo-Based Error Recovery**: Transaction failures are handled via the undo system rather than complex rollback mechanisms

This design optimizes for:
- **Privacy**: Zero plaintext data at rest
- **Performance**: In-memory tree operations and recursive patterns
- **Simplicity**: No complex transaction coordination or connection pooling needed
- **Reliability**: Clean failure modes with automatic recovery

Key design decisions:
- Server-side processing
- Minimal network traffic
- Clean separation of concerns
- Simple, efficient client implementation
- In-memory data structures over database optimization
- Undo/redo for error recovery

## Development

### Setup
1. Install Python dependencies:
```
pip install -r requirements.txt
```
2. Install Node.js dependencies:
```
npm install
```
3. Install Cypress:
```
npm install cypress --save-dev
```
### Running the Application
1. Start the FastAPI server:
```
python app.py
```
2. Visit http://localhost:5000 in your browser

### Running Tests

#### Backend tests:

Unit tests:
```
python -m pytest tests/unit
```

Integration tests: TODO

#### Frontend tests:

Open Cypress Test Runner
```
cd tests/ui
npx cypress open
```

Run tests headlessly
```
cd tests/ui
npx cypress open
```
