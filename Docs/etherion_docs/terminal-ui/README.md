# Etherion Terminal UI (TUI) Guide

## What is the TUI?

The Etherion Terminal UI is a full-featured terminal interface for operators who spend their day in the shell. It's built with [Bubble Tea](https://github.com/charmbracelet/bubbletea), the Go framework for terminal user interfaces, and provides everything you need to manage the Etherion platform without touching a web browser.

Think of it as your ops dashboard—it lives in your terminal, speaks terminal language, and gets out of your way. You can start services, check platform health, onboard new users, manage agents, stream logs, and view job history all from 8 tabbed interfaces.

## Why Does It Exist?

When you're running Etherion on bare metal or in containers, you need a tool that:

1. **Lives in your terminal**: No electron apps, no browser tabs. Just SSH into your server and run `etherion-tui`.
2. **Guides you through setup**: The TUI's Setup Wizard walks you through the 7-step initialization process (check binary, verify `.env`, bootstrap services, migrate database, create admin account, connect OAuth, start the server).
3. **Gives you visibility**: The Dashboard tab shows the health of PostgreSQL, Redis, MinIO, and the API server in real time.
4. **Manages the platform lifecycle**: The Services tab can start and stop platform processes without background process management headaches. The TUI handles process groups and clean termination.
5. **Keeps logs centralized**: The Logs tab streams output from setup and service operations, so you can debug issues without hunting for files.

The TUI is designed for the operator who lives in the terminal—it's fast, responsive, and keyboard-driven.

## Architecture at a Glance

The TUI is structured around the **Elm Architecture**, popularized by the Elm programming language but now standard in Bubble Tea. The pattern is simple and powerful:

- **Model**: Your state (which tab is active, what data is displayed, input fields).
- **Update**: When a message (keystroke, async result, timer tick) arrives, update the model and return any new commands to run.
- **View**: Render the current model to a string and display it on screen.

Messages flow through the system like events. When you press a key, that becomes a message. When an async operation (like checking service health) completes, that result becomes a message. The Update function processes each message, potentially triggering more commands.

The Etherion TUI implements this pattern at two levels:

1. **Root Model** (`RootModel`): The top-level model that routes messages to the active tab and manages global key bindings (number keys to switch tabs, Ctrl+C to quit).
2. **Tab Models**: Eight separate models (Connect, Setup, Chat, Agents, Monitor, OAuth, Logs, Dashboard), each with its own Update and View logic.

When you press "1" or "2" or any number 1-8, the root model switches the active tab. Each tab receives messages only when it's active, reducing noise and keeping logic isolated.

## Getting Started

### Installation

The TUI is bundled with the Python `etherion` package:

```bash
pip install etherion
```

This installs both the `etherion` CLI and the `etherion-tui` binary. The Python wrapper (`etherion_tui/__init__.py`) detects your OS and architecture (Linux/macOS/Windows, amd64/arm64) and runs the correct precompiled Go binary.

### Running the TUI

```bash
etherion-tui
```

On first run:
- If you have no saved credentials, you'll land on the **Connect tab** (login/register).
- If you're already logged in, you'll see the **Dashboard tab**.

### Key Bindings

- **1-8**: Jump to a specific tab (Connect, Setup, Chat, Agents, Monitor, OAuth, Logs, Dashboard)
- **Tab / Shift+Tab**: Cycle through tabs
- **Ctrl+C**: Quit the TUI
- **q**: Quit (except when in Connect or Setup tab, where `q` is disabled so you can't accidentally quit while entering credentials)

Each tab has its own keybindings—check the help bar at the bottom of each tab for details.

## Configuration

The TUI stores your credentials and API server URL in a JSON config file:

```
~/.config/etherion/tui.json
```

This file contains:
- `api_url`: The URL of the Etherion API server (e.g., `http://localhost:8080`)
- `access_token`: Your JWT token (auto-saved after login)
- `email`: Your login email
- `name`: Your display name
- `etherion_bin`: (optional) Explicit path to the `etherion` binary

The TUI loads this config on startup. If the file doesn't exist or is missing keys, sensible defaults are used (API URL defaults to `http://localhost:8080`).

You can override the API URL via the environment variable `ETHERION_API_URL`:

```bash
ETHERION_API_URL=http://192.168.1.100:8000 etherion-tui
```

## Next Steps

- **[architecture.md](architecture.md)**: Deep dive into how Bubble Tea works and how Etherion's TUI is organized.
- **[tabs-reference.md](tabs-reference.md)**: Detailed walkthrough of each tab's purpose and how to use it.
- **[service-lifecycle.md](service-lifecycle.md)**: How the TUI starts, manages, and cleans up platform services.
- **[configuration.md](configuration.md)**: Configuration file format, API client initialization, and cross-platform binary selection.
