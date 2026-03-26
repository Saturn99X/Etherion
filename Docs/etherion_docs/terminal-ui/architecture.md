# Etherion TUI Architecture

## The Elm Architecture: Model → Update → View

Bubble Tea, the framework powering the Etherion TUI, implements the Elm Architecture—a functional programming pattern for building UIs. The pattern is elegant and scales well:

```
┌─────────────────────────────────────┐
│         User Input or Timer          │
│     (keystroke, async result)        │
└─────────────┬───────────────────────┘
              │
              ├── Packaged as a Message (tea.Msg)
              │
              ▼
┌──────────────────────────────────────┐
│     Update(model, msg)               │
│   Returns (newModel, cmd)            │
└──────────────┬───────────────────────┘
               │
               ├── Model is transformed
               ├── Commands may be issued
               │   (e.g., fetch data, start timer)
               │
               ▼
┌──────────────────────────────────────┐
│     View(newModel)                   │
│   Returns a string to display        │
└──────────────┬───────────────────────┘
               │
               ▼
        ┌─────────────┐
        │   Display   │
        │  on Screen  │
        └─────────────┘
```

### Model

The **Model** is the complete application state. It's a struct in Go. Every piece of data needed to render the UI lives in the model.

Example (simplified):

```go
type RootModel struct {
    activeTab int          // which tab (0-7) is shown
    width     int          // terminal width
    height    int          // terminal height
    cfg       *config.Config
    api       *api.Client  // nil until logged in

    connect   ConnectModel
    setup     SetupModel
    chat      ChatModel
    // ... 5 more tab models
}
```

### Update

The **Update** function receives a message and returns a new model. It's a pure function (no side effects). If you need to do something async (query a database, call an API, start a process), you return a Command.

```go
func (m RootModel) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
    switch msg := msg.(type) {
    case tea.KeyMsg:
        if key.Matches(msg, key.NewBinding(key.WithKeys("1"))) {
            m.activeTab = 0  // Switch to tab 1
            return m, nil
        }
    case healthResultMsg:
        // Health check async result arrived
        m.dashboard, _ = m.dashboard.Update(msg)
        return m, nil
    }
    // Delegate to active tab
    switch m.activeTab {
    case 0: // Connect tab
        m.connect, cmd := m.connect.Update(msg)
        return m, cmd
    // ...
    }
}
```

### View

The **View** function takes the model and returns a string—exactly what should be displayed on screen. No side effects; just render.

```go
func (m RootModel) View() string {
    return lipgloss.JoinVertical(lipgloss.Left,
        m.renderTabBar(),        // "1:Connect  2:Setup  3:Chat ..."
        m.renderActiveTab(),     // Delegate to active tab's View()
        m.renderHelp(),          // Help bar at bottom
    )
}
```

### Commands

A **Command** is a function that Bubble Tea will run asynchronously. It returns a message when it completes. Commands let you fetch data, call APIs, or start long-running operations without blocking the UI.

```go
func doLogin(email, password string) tea.Cmd {
    return func() tea.Msg {
        client := api.New(apiURL, "")
        resp, err := client.Login(context.Background(), email, password)
        if err != nil {
            return loginResultMsg{err: err}
        }
        return loginResultMsg{token: resp.AccessToken, email: resp.Email}
    }
}
```

The framework runs this function in a goroutine and sends the returned message back through the main loop. Your Update handler receives it and updates the model.

## Etherion TUI Structure

The Etherion TUI has a two-level hierarchy:

### Level 1: RootModel (Top-Level Orchestration)

`RootModel` is the application's root. It:
- Holds the active tab index
- Owns instances of all 8 tab models
- Routes messages to the active tab (and some messages to specific tabs)
- Handles global key bindings (1-8 to switch tabs, Ctrl+C to quit)
- Runs global timers (e.g., health checks every 3 seconds)

Key code from `/tui/internal/ui/model.go`:

```go
const (
    tabConnect   = iota // 0 - Login
    tabSetup            // 1 - Onboarding wizard
    tabChat             // 2 - Threads + jobs
    tabAgents           // 3 - Agent management
    tabMonitor          // 4 - Job history
    tabOAuth            // 5 - OAuth connections
    tabLogs             // 6 - Scrollable logs
    tabDashboard        // 7 - Health dashboard
    tabCount            // 8
)

type RootModel struct {
    activeTab int
    width     int
    height    int
    cfg       *config.Config
    api       *api.Client

    connect   ConnectModel
    setup     SetupModel
    chat      ChatModel
    agents    AgentsModel
    monitor   MonitorModel
    oauth     OAuthModel
    logs      LogsModel
    dashboard DashboardModel
}
```

When you press "3", the root model sets `activeTab = 2` (Chat). The next render call will invoke `m.chat.View()` instead of the previous tab's View.

### Level 2: Tab Models (Isolated Logic)

Each tab is its own model with Update and View methods. Tabs are independent and unaware of each other. The root model bridges them.

For example, the **Setup tab** (`SetupModel`):

```go
type SetupModel struct {
    step       setupStep  // which of 7 steps we're on
    mode       setupMode  // Docker or Bare Metal
    lines      []string   // output lines from async commands
    running    bool       // is a step currently running?
    lastFailed bool       // did the last step error?
    cfg        *config.Config
    tenantInputs [2]textinput.Model // email + password fields
    tenantFocused int
}
```

This tab manages its own state: which setup step, whether the user is filling in the tenant form, what command output to display. When you press Enter, it doesn't communicate with the Chat tab; it just processes that keystroke locally.

### Message Routing

Not all messages go to the active tab. Some are global:

- **Global messages** (handled by RootModel first):
  - Key bindings (1-8, Tab, Shift+Tab, Ctrl+C)
  - Window resize events
  - Tickers (e.g., health check every 3s)
  - Specific async results (loginResultMsg, healthResultMsg, etc.)

- **Tab-specific messages** (delegated to the active tab):
  - Keys pressed when the tab is active
  - Tab-specific async results

From the root model's Update:

```go
func (m RootModel) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
    // Handle global messages first
    switch msg := msg.(type) {
    case tea.KeyMsg:
        switch {
        case key.Matches(msg, key.NewBinding(key.WithKeys("1"))):
            m.activeTab = tabConnect
            return m, nil
        // ... more 1-8 handlers
        case key.Matches(msg, key.NewBinding(key.WithKeys("ctrl+c"))):
            return m, tea.Quit
        }

    case healthResultMsg:
        // Specific message → dashboard tab
        m.dashboard, _ = m.dashboard.Update(msg)
        return m, tea.Batch(cmds...)

    case loginResultMsg:
        // Specific message → connect tab
        m.connect, _ = m.connect.Update(msg)
        if msg.err == nil {
            // Update root model with new credentials
            m.cfg.AccessToken = msg.token
            m.api = api.New(m.cfg.APIURL, msg.token)
            m.activeTab = tabDashboard
        }
        return m, tea.Batch(cmds...)
    }

    // Then delegate to active tab
    switch m.activeTab {
    case tabConnect:
        m.connect, cmd := m.connect.Update(msg)
        return m, cmd
    case tabSetup:
        m.setup, cmd := m.setup.Update(msg)
        return m, cmd
    // ... etc
    }
}
```

This separation keeps tabs focused. The Setup tab doesn't know about OAuth or Chat—it just knows how to process setup steps.

## The Logs Sink

One important detail: the **Logs tab** captures output from async operations (setup commands, service startup).

When the Setup tab runs a command (like `etherion migrate`), the runner streams its output line-by-line. Each line is wrapped in a `lineMsg` and sent to the root model:

```go
case lineMsg:
    m.logs, _ = m.logs.Update(logAppendMsg{line: msg.line})
    if msg.tab == tabSetup {
        var c tea.Cmd
        m.setup, c = m.setup.Update(msg)
        cmds = append(cmds, c)
    }
```

This way, any tab that runs a long-lived process can have its output captured and displayed in the Logs tab. The user switches to Logs (press 7) to monitor progress.

## Initialization Sequence

When you start the TUI:

1. **Config loads** (or defaults if missing)
2. **RootModel is created** with either tabConnect or tabDashboard as the starting tab
3. **Init() is called** on the root model, which:
   - Returns a batch of commands (dashboard health check, ticker)
4. **The event loop starts**: Bubble Tea enters its main loop, waiting for messages

From `main.go`:

```go
func main() {
    cfg, err := config.Load()
    if err != nil {
        cfg = &config.Config{APIURL: "http://localhost:8000"}
    }

    p := tea.NewProgram(
        ui.NewRootModel(cfg),
        tea.WithAltScreen(),        // Use alternate screen buffer
        tea.WithMouseCellMotion(),  // Enable mouse support
    )
    if _, err := p.Run(); err != nil {
        fmt.Fprintf(os.Stderr, "error: %v\n", err)
        os.Exit(1)
    }
}
```

This is the entire entry point. Bubble Tea handles the rest: the event loop, rendering, handling Ctrl+C.

## Why This Matters

This architecture gives you:

1. **Testability**: Update and View are pure functions. You can test them with sample data and no I/O.
2. **Composability**: Tabs are independent models. You can reuse them, test them in isolation, or replace them.
3. **Clarity**: Data flows one direction (messages → Update → View). No surprise mutations or hidden state.
4. **Scalability**: Adding a new tab is just a new model and a new case in the root model's Update and View.
5. **Responsiveness**: Async operations (commands) don't block the UI. The entire interface stays responsive.

When you're debugging the TUI, you're not hunting for where state lives—it's all in the models. When you want to understand how a tab works, you look at that tab's Update and View. Clean, predictable, and easy to reason about.
