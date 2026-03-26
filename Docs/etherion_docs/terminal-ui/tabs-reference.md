# Etherion TUI Tabs Reference

The Etherion TUI has 8 tabs, each serving a specific purpose in managing the platform. Press 1-8 or use Tab/Shift+Tab to navigate.

## Tab 1: Connect (Login / Register)

**Purpose**: Authenticate with the Etherion API server. Also handles account registration for the very first admin user.

### What You See

A form with three fields:
- **Server**: The API URL (e.g., `http://127.0.0.1:8000`). Pre-filled from config or `ETHERION_API_URL` env var.
- **Email**: Your login email.
- **Password**: Your password (shown as dots).

Two buttons let you toggle between **Login** and **Register** modes. Press Ctrl+R to switch.

### Login Mode

Enter your existing credentials and press Enter. The TUI communicates with the API, verifies your JWT, and stores the token in `~/.config/etherion/tui.json`.

If login succeeds, you're taken to the Dashboard tab.

### Register Mode

Used only on first setup, before any admin account exists. The register flow is special:

1. Press Ctrl+R to enter Register mode.
2. Fill in email and password. Note: **The server doesn't need to be running yet.** Registration creates a local tenant.
3. Press Enter. The TUI runs `etherion create-tenant --email <email> --password <password>` in the background.
4. If successful, you're switched to Login mode with credentials pre-filled. Log in as usual.

### Key Bindings

- **Tab / Up / Down**: Move between fields
- **Enter**: Submit (or advance to next field if not on password field)
- **Ctrl+R**: Toggle Login ↔ Register
- **Ctrl+C**: Quit

### Behind the Scenes

When you log in, the Connect tab calls `api.Login()`, which sends a POST request to the server:

```go
func (m *ConnectModel) doLogin() tea.Cmd {
    server := strings.TrimSpace(m.inputs[connectFieldServer].Value())
    email := strings.TrimSpace(m.inputs[connectFieldEmail].Value())
    password := m.inputs[connectFieldPassword].Value()

    m.loading = true
    m.status = StyleMuted.Render("Connecting…")
    m.cfg.APIURL = server

    return func() tea.Msg {
        client := api.New(server, "")
        resp, err := client.Login(context.Background(), email, password)
        if err != nil {
            return loginResultMsg{err: err}
        }
        return loginResultMsg{token: resp.AccessToken, email: resp.Email, name: resp.Name}
    }
}
```

The RootModel receives the `loginResultMsg` and, if successful, saves the token, creates a new API client, and switches to the Dashboard tab.

---

## Tab 2: Setup (Onboarding Wizard)

**Purpose**: Walk you through the 7-step initialization process, from binary verification to platform launch.

### What You See

A menu with two modes (Docker or Bare Metal), followed by a 7-step wizard:

1. **Find etherion binary**: Checks if `etherion` CLI is in your PATH.
2. **Check .env file**: Verifies `.env` exists in the current directory.
3. **Bootstrap services**: Runs `docker compose up -d` (Docker mode) or checks/starts PostgreSQL, Redis, MinIO (Bare Metal mode).
4. **Run migrations**: Executes `etherion migrate` to set up database schema.
5. **Create admin account**: Inline form for email and password. Same as the Register flow in the Connect tab.
6. **Connect OAuth**: Manual step. Prompts you to switch to the OAuth tab (tab 6) to add OAuth providers. Press Enter to continue.
7. **Launch server**: Starts `etherion serve` in the background (detached process).

Each step shows progress with icons:
- **✓ Green**: Completed
- **→ Yellow**: Current step
- **Gray**: Not yet reached

### Docker vs. Bare Metal

At the start, you choose:
- **Docker Mode** (default): Uses docker-compose. Requires Docker to be installed and running.
- **Bare Metal Mode**: Expects PostgreSQL, Redis, and MinIO to be running as systemd services. The wizard polls TCP ports and tries `systemctl start` if services are down.

### Bare Metal Mode Details

In Bare Metal mode, step 3 is extended. The wizard checks three services:

```go
services := []svcDef{
    {
        name:  "PostgreSQL",
        addr:  "127.0.0.1:5432",
        units: []string{"postgresql", "postgresql.service", "postgres"},
    },
    {
        name:  "Redis",
        addr:  "127.0.0.1:6379",
        units: []string{"redis", "redis.service", "redis-server"},
    },
    {
        name:  "MinIO",
        addr:  "127.0.0.1:9000",
        units: []string{"minio", "minio.service"},
    },
}
```

For each service, it:
1. Tries to connect via TCP (2-second timeout)
2. If reachable, marks ✓
3. If not, tries `systemctl start <unit>` for each listed unit name
4. Waits 4 seconds and retries
5. If still unreachable, shows install instructions

If any service fails, the wizard halts and shows the error. You can fix it (install missing packages, start services manually) and press Enter to retry.

### Output Logs

All command output is captured and displayed in a scrollable log. You can see what `etherion bootstrap` is doing, what `etherion migrate` is outputting, etc. This log also appears in the Logs tab (tab 7) if you switch there.

### Key Bindings

- **Tab 1 (mode selection)**: Left/Right to select Docker or Bare Metal, Enter to start
- **During steps**: Enter to advance to the next step
- **If a step fails**: Fix the issue and press Enter to retry
- **r**: Restart the entire wizard
- **Ctrl+C**: Quit (will terminate the TUI, not the background server)

### Behind the Scenes

The Setup tab uses `runner.StartDetached()` to launch `etherion serve`. This starts the server in a detached process group so it keeps running after the TUI exits (see [service-lifecycle.md](service-lifecycle.md) for details).

---

## Tab 3: Chat (Run Jobs / Threads)

**Purpose**: Create and manage chat threads, run inference jobs against Agents.

### What You See

A list of threads (conversations) with metadata:
- Thread ID
- Most recent message
- Timestamp

You can select a thread to view its messages and run new jobs.

### Key Bindings

- **Up / Down** or **j / k**: Navigate threads
- **Enter**: Open selected thread
- **n**: Create new thread
- **d**: Delete thread (with confirmation)
- **Ctrl+C**: Quit

### Behind the Scenes

The Chat tab queries the API for threads and messages:

```go
type ChatModel struct {
    threads []Thread
    selected int
    api *api.Client
}
```

When you open a thread, it fetches the message history and prepares to send new requests.

---

## Tab 4: Agents (View / Manage)

**Purpose**: List agents, view their configurations, enable/disable them.

### What You See

A table of agents with columns:
- Agent name
- Status (enabled/disabled)
- Model
- Token limit
- Memory type

You can select an agent to view details or disable/enable it.

### Key Bindings

- **Up / Down**: Navigate agents
- **Enter**: View details
- **e**: Toggle enable/disable
- **Ctrl+C**: Quit

### Behind the Scenes

Queries the API's GraphQL schema for available agents:

```go
type AgentsModel struct {
    agents []Agent
    selected int
    api *api.Client
}
```

---

## Tab 5: Monitor (Job History)

**Purpose**: View completed and running jobs, their status, output, and results.

### What You See

A list of jobs with:
- Job ID
- Started time
- Status (running, completed, failed)
- Agent used
- Exit code (if done)

Select a job to view its full output and result.

### Key Bindings

- **Up / Down**: Navigate jobs
- **Enter**: View job details
- **r**: Refresh list
- **Ctrl+C**: Quit

### Behind the Scenes

Queries the API for job history:

```go
type MonitorModel struct {
    jobs []Job
    selected int
    api *api.Client
}
```

---

## Tab 6: OAuth (Connect External Providers)

**Purpose**: Link OAuth providers (GitHub, Google, etc.) so users can log in via those services.

### What You See

A list of configured OAuth providers:
- Provider name (GitHub, Google, etc.)
- Status (connected / not configured)
- Last updated time

### Workflow

1. Press Enter on an unconfigured provider
2. The TUI displays a setup form with two fields:
   - **Client ID** (from your OAuth app)
   - **Client Secret** (from your OAuth app)
3. Fill them in and press Enter
4. The TUI sends them to the API

The API stores the credentials encrypted.

### Key Bindings

- **Up / Down**: Navigate providers
- **Enter**: Configure selected provider
- **d**: Disconnect provider
- **Ctrl+C**: Quit

---

## Tab 7: Logs (Real-Time Output Stream)

**Purpose**: Monitor output from long-running operations (setup commands, service startup).

### What You See

A scrolling log of lines from any active background process. Lines are appended as they arrive.

The header shows:
- **follow: on/off** (Green if following, gray if not)

The footer shows keyboard shortcuts.

### How It Works

When the Setup tab runs `etherion migrate`, the output is streamed line-by-line and appended to the Logs tab's buffer. You can switch to the Logs tab anytime to see progress.

The TUI keeps the last 2000 lines in memory to avoid unbounded growth.

### Key Bindings

- **f**: Toggle auto-follow (if on, scrolls to the bottom as new lines arrive; if off, stays at your scroll position)
- **Up / Down / Page Up / Page Down**: Scroll
- **Ctrl+C**: Quit

### Behind the Scenes

The Logs tab uses a Bubble Tea `viewport` component to handle scrolling:

```go
type LogsModel struct {
    viewport viewport.Model
    lines    []string
    follow   bool
}

func (m LogsModel) Update(msg tea.Msg) (LogsModel, tea.Cmd) {
    switch msg := msg.(type) {
    case logAppendMsg:
        m.lines = append(m.lines, msg.line)
        if len(m.lines) > 2000 {
            m.lines = m.lines[len(m.lines)-2000:]
        }
        m.viewport.SetContent(strings.Join(m.lines, "\n"))
        if m.follow {
            m.viewport.GotoBottom()
        }
    }
    // ... handle scrolling keys
}
```

---

## Tab 8: Dashboard (Platform Health)

**Purpose**: At-a-glance view of platform service health.

### What You See

A table with one row per service:
- **PostgreSQL**: TCP check to localhost:5432
- **Redis**: TCP check to localhost:6379
- **MinIO**: TCP check to localhost:9000
- **API**: HTTP connectivity check to the Etherion API server

Each row shows:
- **Icon**: ✓ if reachable, ✗ if not
- **Name**: Service name
- **Detail**: Host:port or error message
- **Latency**: Response time in milliseconds

At the bottom, the timestamp of the last check.

### How It Works

Every 3 seconds, the root model's ticker fires and calls `doHealthCheck()`. This performs TCP connects (with a 2-second timeout) to each service and returns the results. The Dashboard tab receives a `healthResultMsg` and updates its display.

If a service is unreachable, the icon turns red and shows the error (e.g., "connection refused").

### Configuration

The health check reads service endpoints from `.env`:
- `DATABASE_URL` (or defaults to `localhost:5432`)
- `REDIS_URL` (or defaults to `localhost:6379`)
- `MINIO_ENDPOINT` (or defaults to `localhost:9000`)
- `API_HOST` and `API_PORT` (or defaults to `localhost:8080`)

### Key Bindings

- **r**: Manually refresh (trigger a health check immediately)
- **Ctrl+C**: Quit

### Behind the Scenes

```go
func doHealthCheck(env map[string]string) tea.Cmd {
    return func() tea.Msg {
        results := []healthEntry{
            tcpCheck("PostgreSQL", env["DATABASE_URL"], "localhost:5432"),
            tcpCheck("Redis", env["REDIS_URL"], "localhost:6379"),
            tcpCheck("MinIO", env["MINIO_ENDPOINT"], "localhost:9000"),
            httpCheck("API", env),
        }
        return healthResultMsg{results: results}
    }
}
```

Each check is a TCP dial with a timeout. If it succeeds, we record the round-trip time. If it fails, we record the error.

---

## Tab Interaction Examples

### Scenario 1: First-Time Setup

1. Run `etherion-tui`. You land on **Tab 1 (Connect)** because you're not logged in.
2. Register mode is on (see the "Register (first time?)" button). Fill in your email and password, press Enter.
3. The TUI runs `etherion create-tenant` and switches you to Login mode.
4. Login succeeds. You're now on **Tab 8 (Dashboard)**.
5. Go to **Tab 2 (Setup)** to begin the wizard. Choose Docker or Bare Metal.
6. The wizard runs through 7 steps. Output is streamed to **Tab 7 (Logs)**. At step 6 (OAuth), the wizard prompts you to go to **Tab 6 (OAuth)** to configure providers.
7. After setup completes, the server is running in the background.

### Scenario 2: Running a Job

1. Go to **Tab 3 (Chat)** to create or open a thread.
2. Create a new thread, add a message, select an agent.
3. Send the message. The job starts running.
4. Go to **Tab 7 (Logs)** to watch the agent's output in real-time.
5. When done, go to **Tab 5 (Monitor)** to see the job in the job history and view its result.

### Scenario 3: Monitoring Health

1. Go to **Tab 8 (Dashboard)** to see current service health.
2. If something is red, check the error message.
3. Fix it (restart a service, check config, etc.).
4. Press **r** on the Dashboard to manually refresh, or wait 3 seconds for the next auto-check.

All tab interactions are independent. You can jump between tabs with single keypresses, and each tab maintains its own state (scroll position, selected item, etc.).
