# etherion-tui

Terminal UI for the [Etherion](https://github.com/Saturn99X/Etherion) AI platform.

## Install

```bash
pip install etherion-tui
```

This also installs `etherion` as a dependency — the full platform CLI and runtime.

## Usage

```bash
etherion-tui
```

Launches a full-screen TUI with 8 tabs:

| Tab | Key | Description |
|-----|-----|-------------|
| Connect | `1` | Login with email/password, configure server URL |
| Setup | `2` | Step-by-step onboarding wizard |
| Chat | `3` | Threads and jobs |
| Agents | `4` | Agent team management |
| Monitor | `5` | Job history and status |
| OAuth | `6` | Connect GitHub, Google, Slack, Notion, Jira, HubSpot, Linear, Shopify |
| Logs | `7` | Live log stream |
| Dashboard | `8` | Infrastructure health |

## Requirements

- Linux x86-64 (this wheel contains a native binary)
- Python 3.11+
