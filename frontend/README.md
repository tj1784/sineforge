# CineForge Frontend

React, Vite, and TypeScript provide the only user-facing interface for the
unified Sineforge + BlokeyUI application.

## Run

Normally start the complete app from the repository root:

```powershell
.\start-cineforge.cmd
```

For frontend-only development:

```powershell
npm install
npm run dev
```

The frontend calls FastAPI at `http://127.0.0.1:8010` by default. Override it
only with a trusted loopback origin:

```powershell
$env:VITE_CINEFORGE_API_BASE_URL="http://127.0.0.1:8010"
```

## Scope

The UI owns project planning and the complete Engine workspace. The native API
Runner loads, saves, edits, validates, queues, monitors, interrupts, and previews
API-format ComfyUI workflows. Engine start/restart and VRAM controls are visible
inside Sineforge. Empty workspaces can open `/engine` without first creating a
project.

The UI does not link to or depend on the ComfyUI canvas, does not use the legacy
ComfyAPI Runner, and does not provide public prompt submission. FastAPI remains
the trusted boundary for path validation, workflow admission, queue mutation,
engine lifecycle, and output access.

## Verify

```powershell
npm test -- --run
npm run build
npx eslint src
```
