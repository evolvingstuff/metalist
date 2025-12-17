# Note Management System

Layered view of the hierarchical note system.

```mermaid
graph TD
    subgraph "Frontend"
        UI[Note UI]
        State[ModeContext]
        Actions[User Actions<br/>(keyboard/mouse)]
    end

    subgraph "API Layer"
        NotesAPI[Notes Routes<br/>/api2/notes/*]
        ViewAPI[View Route<br/>POST /api2/notes/view]
    end

    subgraph "Application Layer"
        Cmds[Cmd* Usecases]
        Snapshot[Snapshot Builder]
    end

    subgraph "Services"
        Store[NoteStore]
        Cache[Content Cache]
        Undo[Undo State]
        Sync[Sync + Locks]
    end

    subgraph "Persistence"
        SQL[sqlite helpers]
        DB[(SQLite DB)]
    end

    UI --> State
    Actions --> State
    State --> NotesAPI
    State --> ViewAPI

    NotesAPI --> Cmds
    ViewAPI --> Snapshot

    Cmds --> Store
    Cmds --> Undo
    Cmds --> Sync
    Cmds --> SQL

    Snapshot --> Store
    Snapshot --> Cache
    Snapshot --> Sync

    SQL --> DB
    Cache -.-> DB
```
