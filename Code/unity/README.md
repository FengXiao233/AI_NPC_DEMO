# NPC Social RPG Unity 3D

This is the Unity 3D migration target for the original Godot 2D demo.

## What Was Migrated

- Runtime-generated 3D village scene with five areas: village entrance, square, market, hunting forest, and rest area.
- Player movement with `WASD` / arrow keys and proximity interaction with `E`.
- Seven NPCs synced from the existing FastAPI backend.
- Area hotspots for transitions, inspection points, and NPC focus.
- Dialogue submission, dialogue history, tick advancement, auto tick, planning/execution, reset, and world-event injection.
- World resources, dynamic entities, event log, and economy summary display.

## Open The Project

Use the installed editor:

```powershell
& 'D:\Learing\2022.3.45f1c1\Editor\Unity.exe' -projectPath 'C:\Users\ZhuanZ.DESKTOP-PH97BKO\Desktop\AIGameDesign\Code\unity'
```

Open `Assets/Scenes/VillageWatch3D.unity` and press Play.

## Backend

Start the existing Python service before pressing Play:

```powershell
cd C:\Users\ZhuanZ.DESKTOP-PH97BKO\Desktop\AIGameDesign\Code
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The Unity controller defaults to `http://127.0.0.1:8000`.

## Controls

- `WASD` / arrow keys: move player
- `E`: interact with nearby NPC or hotspot
- `T`: advance one simulation tick
- `O`: inject suspicious arrival event
- `P`: plan and execute selected NPC task
- `R`: reset world
