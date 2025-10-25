# Electron Desktop App Implementation

## Overview
The Electron app serves as the free tier of MetaList, providing a full-featured local experience that acts as both a standalone tool and a funnel to the paid cloud subscription.

## Architecture

### Current Web Architecture
- **Backend**: FastAPI server (Python)
- **Frontend**: Server-side rendered templates (Mako) + vanilla JavaScript
- **Database**: SQLite
- **Server**: Runs on localhost:8000

### Electron Wrapper Approach
The Electron app will wrap the existing FastAPI application with minimal changes:

```
electron-app/
├── main.js              # Electron main process
├── preload.js           # Security bridge
├── package.json         # Electron dependencies
├── dist/                # Packaged Python backend
│   └── metalist/        # PyInstaller output
└── build/               # Platform installers
```

## Implementation Steps

### Phase 1: Basic Electron Shell (1-2 days)
1. Create Electron wrapper that launches FastAPI server
2. Package Python backend with PyInstaller
3. Handle server lifecycle (start/stop with app)
4. Basic window management

### Phase 2: Native Integration (2-3 days)
1. System tray integration
2. Global hotkeys for quick capture
3. Native menus
4. Auto-start option
5. Native notifications

### Phase 3: Distribution (1-2 days)
1. Code signing setup
2. Auto-update mechanism
3. Platform installers (DMG, EXE, AppImage)
4. Download page on website

## Technical Details

### Electron Main Process (main.js)
```javascript
const { app, BrowserWindow } = require('electron');
const { spawn } = require('child_process');
const path = require('path');

let mainWindow;
let backendProcess;

function startBackend() {
  // Start packaged Python backend
  const backendPath = path.join(__dirname, 'dist', 'metalist', 'metalist');
  backendProcess = spawn(backendPath, [], {
    env: { ...process.env, METALIST_PORT: '8000' }
  });
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js')
    }
  });
  
  // Wait for backend to be ready, then load
  setTimeout(() => {
    mainWindow.loadURL('http://localhost:8000');
  }, 2000);
}

app.whenReady().then(() => {
  startBackend();
  createWindow();
});
```

### Python Backend Packaging
Using PyInstaller to create standalone executable:
```bash
pyinstaller --onefile \
  --hidden-import=uvicorn \
  --hidden-import=fastapi \
  --add-data "templates:templates" \
  --add-data "static:static" \
  app.py
```

### Data Storage
- **Free/Local Mode**: SQLite database in user's app data directory
- **Cloud Mode**: When subscription active, sync local SQLite with cloud

## Free vs Paid Features

### Always Free (Local)
- All core features
- Unlimited notes
- Full text search
- Tag implications
- Import/export
- Local SQLite database

### Paid (Cloud Subscription)
- Multi-device sync
- Web access
- Automatic backups
- Share notes (future)
- Mobile apps (future)
- Priority support

### Gentle Monetization
- Occasional popup after 30 days: "Enjoying MetaList? Enable cloud sync"
- Small "Enable Sync" button in UI
- Backup reminder after 100+ notes
- No feature limitations or data hostage

## Migration Path

### Free → Paid
1. User clicks "Enable Cloud Sync"
2. Create account / login
3. Local database uploads to cloud
4. Seamless transition to synced mode

### Paid → Free
1. Subscription ends
2. Final sync to local
3. Continue using locally
4. Data remains accessible

## Development Effort

### Minimum Viable Electron App
- **Time**: 1-2 days
- **Deliverable**: Basic working desktop app
- **Platforms**: macOS initially, then Windows/Linux

### Production-Ready Version
- **Time**: 1 week total
- **Includes**: Auto-update, installers, code signing
- **Polish**: Native feel, system integration

## Benefits

### For Users
- No setup required (vs running Python server)
- Feels like "real" desktop software  
- Data stays local unless they choose cloud
- Natural upgrade path when ready

### For Business
- Lower barrier to entry than web trial
- Extended trial period (use free forever)
- Higher conversion due to investment (time/data)
- Clear value proposition for upgrade

## Next Steps
1. Validate FastAPI can be packaged with PyInstaller
2. Create minimal Electron proof-of-concept
3. Test on target platforms
4. Design upgrade flow UX
5. Implement gentle monetization nudges