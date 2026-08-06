# Restart Server Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a Windows batch file that restarts Backstage on localhost port 8090.

**Architecture:** A root-level batch file finds listening TCP processes on port 8090 and terminates them before starting `main.py` through the project virtual environment. The server runs in its own command window and the default browser receives the local URL after a short delay.

**Tech Stack:** Windows batch, `netstat`, `taskkill`, Python virtual environment.

## Global Constraints

- The script must target only TCP port `8090`.
- It must start `.venv\\Scripts\\python.exe main.py` with `PORT=8090`.
- No existing user files are modified.

---

### Task 1: Server restart launcher

**Files:**
- Create: `restart_server.bat`
- Test: manual Windows command-prompt smoke test

**Interfaces:**
- Consumes: `.venv\\Scripts\\python.exe` and `main.py` at the repository root.
- Produces: `restart_server.bat`, executable from Windows Explorer or a command prompt.

- [ ] **Step 1: Confirm the virtual-environment interpreter exists**

Run: `Test-Path .venv\\Scripts\\python.exe`

Expected: `True`.

- [ ] **Step 2: Create the launcher**

```bat
@echo off
setlocal
set "PORT=8090"
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":%PORT%" ^| findstr "LISTENING"') do taskkill /PID %%P /F >nul 2>&1
start "Backstage server" cmd /k "set PORT=%PORT%&& .venv\\Scripts\\python.exe main.py"
timeout /t 2 /nobreak >nul
start "" "http://localhost:%PORT%"
endlocal
```

- [ ] **Step 3: Launch the file and verify it is listening**

Run: `cmd /c restart_server.bat` then `netstat -ano | findstr :8090`

Expected: exactly one `LISTENING` entry for port `8090` after the startup delay.

- [ ] **Step 4: Verify restart behavior**

Run: `cmd /c restart_server.bat` a second time, then `netstat -ano | findstr :8090`.

Expected: the previous listener has been terminated and exactly one replacement listener remains.

- [ ] **Step 5: Commit**

```bash
git add restart_server.bat
git commit -m "chore: add local server restart script"
```
