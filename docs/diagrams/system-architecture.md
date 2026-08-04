# System Architecture

High-level overview of MetaList3 components and their relationships.

```mermaid
graph TB
    subgraph "Client Browser"
        UI[UI + DOM<br/>Notes, Search, Modals]
        MM[ModeManager<br/>State Orchestration]
        AC[API Client<br/>fetch()]
        Auth[Auth Module<br/>Token + Tab Id]
        CM[Connectivity Monitor<br/>Status Polling]
    end

    subgraph "FastAPI App"
        MW[AuthMiddleware]
        Router[APIRouters<br/>/api2/*]
        Static[Static Files]
        Templates[Mako Templates<br/>SSR]
    end

    subgraph "Application Layer"
        Cmds[Usecases Cmd*<br/>create/move/update/undo]
        Snap[Snapshot Builder<br/>/notes/view]
    end

    subgraph "Services"
        AuthSvc[AuthService]
        TokenSvc[TokenService<br/>one active session per namespace]
        Store[NoteStore<br/>in-memory graph]
        Cache[Content Cache<br/>decrypted content]
        Undo[Undo State]
        Sync[Sync UUID + Locks]
        Crypto[Encryption Service<br/>AES-GCM + Argon2id]
    end

    subgraph "DB Layer"
        SQL[sqlite helpers<br/>notes_sql/settings_sql]
        DB[(SQLite DB)]
    end

    UI --> MM
    MM --> AC
    Auth --> AC
    CM --> AC

    AC --> MW
    MW --> Router

    Router --> Templates
    Router --> Static

    Router --> Cmds
    Router --> Snap

    Snap --> Store
    Snap --> Cache
    Snap --> Sync

    Cmds --> Store
    Cmds --> Undo
    Cmds --> Sync
    Cmds --> SQL

    Router --> AuthSvc
    AuthSvc --> TokenSvc
    AuthSvc --> Crypto

    SQL --> DB
    Crypto --> DB
    Cache -.-> DB
```
