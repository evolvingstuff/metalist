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

Key design decisions:
- Server-side processing
- Minimal network traffic
- Clean separation of concerns
- Simple, efficient client implementation

## Development

### Setup
1. Install Python dependencies (see requirements.txt)
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
```
python -m pytest tests
```

#### Frontend tests:

Open Cypress Test Runner
```
npx cypress open
```

Run tests headlessly
```
npx cypress run
```
