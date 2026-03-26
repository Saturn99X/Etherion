# Etherion TUI: Service Lifecycle Management

## The Problem: Detached Processes

When the Etherion TUI starts the server (at the end of the Setup wizard), it needs to ensure the server keeps running after the TUI exits. The naive approach—starting a subprocess and waiting for it to complete—doesn't work because:

1. The subprocess inherits the TUI's process group
2. If the TUI exits (Ctrl+C), the entire process group gets a SIGTERM signal
3. The subprocess dies along with the TUI

We solve this with **process group detachment** using the `setsid` system call on Unix systems.

## Starting Services: StartDetached()

The TUI uses `runner.StartDetached()` to launch long-running services. This function exists in two versions:

### Unix Version (`detach_unix.go`)

```go
//go:build !windows

package runner

import (
    "os/exec"
    "syscall"
)

func StartDetached(name string, args []string, env []string) error {
    cmd := exec.Command(name, args...)
    if len(env) > 0 {
        cmd.Env = env
    }
    cmd.SysProcAttr = &syscall.SysProcAttr{Setsid: true}
    return cmd.Start()
}
```

The key line is:

```go
cmd.SysProcAttr = &syscall.SysProcAttr{Setsid: true}
```

This tells the OS to create the subprocess in a new session (`setsid` = "set session ID"). The subprocess becomes the leader of its own process group, independent of the TUI's process group.

### What `setsid` Does

On Unix (Linux, macOS, BSD):

1. **Creates a new process group**: The subprocess gets a new PID for its process group.
2. **Detaches from the TTY**: The subprocess is no longer associated with the terminal that launched it.
3. **Ignores parent group signals**: When the TUI's process group receives SIGTERM (e.g., Ctrl+C), the subprocess doesn't receive it.

Result: The subprocess runs independently, even after the TUI exits.

### Invocation

During the Setup tab's step 7 (Launch server), the Setup tab calls:

```go
case sStepServe:
    m.step = sStepServe
    m.running = true
    m.lines = append(m.lines, StyleHeader.Render("Starting: etherion serve (background)"))
    cfg := m.cfg
    return m, func() tea.Msg {
        bin, ok := cfg.EtherionBin()
        if !ok {
            return setupDoneMsg{err: fmt.Errorf("etherion binary not found")}
        }
        if err := runner.StartDetached(bin, []string{"serve"}, nil); err != nil {
            return setupDoneMsg{err: err}
        }
        return setupDoneMsg{extra: StyleMuted.Render("  Server starting in background…")}
    }
```

This is wrapped in a command (async function), so it doesn't block the UI. It calls `etherion serve` with the `Setsid: true` flag and returns immediately. The server starts in the background.

## Verifying Detachment

After the TUI launches the server, you can verify it's truly detached:

1. Run `etherion-tui`
2. Go through the setup wizard to step 7
3. Wait for "Server starting in background…" to appear
4. Press Ctrl+C to exit the TUI
5. Open another terminal and run:

```bash
ps aux | grep etherion
```

You should see a `etherion serve` process still running, even though the TUI is gone. The server process no longer has the TUI as its parent.

## Process Tree Before and After

### Before: Naive Approach (Process Inherits Parent Group)

```
Shell (bash)
├─ etherion-tui
│  └─ etherion serve  ← in the same process group as etherion-tui
│
(If TUI exits via Ctrl+C, entire group gets SIGTERM → etherion serve dies too)
```

### After: With setsid (Detached Process)

```
Shell (bash)
├─ etherion-tui  (process group PID 1234)
│  └─ [executes setsid, then exits TUI]
│
etherion serve  (process group PID 5678, independent)
│  └─ (runs forever, immune to shell Ctrl+C)
```

## Lifecycle in the Setup Wizard

The full lifecycle looks like this:

1. **Step 1-4**: Verify binary, check .env, bootstrap services, run migrations. These are short-lived commands that complete, and the TUI waits for them.

2. **Step 5**: Create tenant. Another short-lived command.

3. **Step 6**: OAuth setup. Manual step; TUI just waits for you to press Enter.

4. **Step 7**: Start server.
   - TUI calls `runner.StartDetached("etherion", ["serve"], nil)`
   - `setsid` creates a new process group for the server
   - Server is now independent
   - TUI immediately reports success (doesn't wait for server to start)

5. **Step 8 (Done)**: Display success message with next steps.

If you exit the TUI at step 7 or later, the server keeps running. The next time you run `etherion-tui`, it will detect that it's already logged in and go straight to the Dashboard tab, where you'll see the server is up (green check for API health).

## Dashboard Health Checks

The Dashboard tab (tab 8) polls service health every 3 seconds. This is how it detects when the server has started after the Setup wizard.

From `model.go`:

```go
func (m RootModel) Init() tea.Cmd {
    return tea.Batch(
        m.dashboard.Init(),
        tickEvery(3*time.Second),
    )
}

func (m RootModel) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
    switch msg := msg.(type) {
    case tickMsg:
        cmds = append(cmds, tickEvery(3*time.Second))
        if m.activeTab == tabDashboard {
            cmds = append(cmds, doHealthCheck(m.dashboard.env))
        }
    // ...
    }
}
```

Every 3 seconds, a ticker fires. If you're viewing the Dashboard, a health check is triggered. The health check does TCP dials to PostgreSQL, Redis, MinIO, and the API server.

So the workflow is:

1. Setup wizard launches `etherion serve` via `StartDetached`
2. Server starts in the background
3. You press Enter to finish the wizard
4. TUI switches to Dashboard
5. After 3 seconds, the health check runs
6. Health check finds API server now reachable → Dashboard shows green check
7. Setup is complete

## Why Not Use Shell Features?

You might think: "Why not just run `etherion serve &` from the shell?" or `nohup etherion serve &`?

The TUI can't rely on shell features because:

1. **It's a standalone binary**: Users run `etherion-tui`, not a shell script. The TUI is the parent process.
2. **Control**: The TUI needs explicit control over process creation and signaling. Shell job control is too implicit.
3. **Portability**: `setsid` works on all Unix systems. Shell `&` behavior varies.

By using `setsid` directly in Go, the TUI ensures portable, reliable detachment across Linux, macOS, and BSD.

## Windows Behavior

On Windows, the TUI's approach is different. Windows doesn't have process groups in the same way, and `setsid` doesn't exist. Instead, the detach code uses a build tag:

From `detach_unix.go`:
```go
//go:build !windows
```

On Windows, a separate file would define `StartDetached` to use Windows-specific APIs (e.g., `syscall.ForkExec` with `CREATE_NEW_PROCESS_GROUP`). However, in the current codebase, Windows support may be limited—the primary focus is Linux and macOS.

## Stopping Services (Future Work)

The current TUI starts services but doesn't have explicit "kill" functionality. The intended workflow is:

1. Setup wizard starts the server
2. Server runs until you manually stop it (or reboot)
3. If you run the setup wizard again, it re-runs steps 1-7, potentially starting a second instance

In a future iteration, a "Services" tab could be added to:
- List running Etherion processes
- Display their PIDs and uptime
- Offer "Stop" or "Restart" buttons

Such a tab would use `syscall.Kill()` to send SIGTERM to running processes and track their exit status.

## Debugging

If you suspect a service isn't actually detached:

1. Start the TUI and run through setup
2. Exit the TUI (Ctrl+C)
3. In another terminal, check if `etherion serve` is still running:

```bash
pgrep -f "etherion serve"
```

If it returns a PID, the server is running. If it returns nothing, the server died (check the TUI's log output for errors).

4. Check the server's process group:

```bash
ps -o pid,ppid,pgid,cmd | grep etherion
```

If the `pgid` (process group ID) is different from the shell's PGID, the server is truly detached.

## Summary

The TUI manages service lifecycle by:

1. **Launching short-lived operations** (setup steps 1-6) with `runner.RunCommand()`, which waits for completion
2. **Launching the server** (step 7) with `runner.StartDetached()`, which uses `setsid` on Unix to create an independent process group
3. **Monitoring via health checks**: The Dashboard polls services every 3 seconds to detect when they're ready
4. **No cleanup on exit**: The TUI doesn't need to clean up because the server is detached and survives TUI exit

This design lets the operator use `etherion-tui` to bootstrap the platform and then close the terminal, confident that the server will keep running.
