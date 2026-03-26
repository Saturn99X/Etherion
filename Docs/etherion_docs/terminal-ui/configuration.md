# Etherion TUI: Configuration

## Configuration File Location

The TUI stores configuration in:

```
~/.config/etherion/tui.json
```

This file is created automatically on first login and persists across TUI sessions.

## Configuration File Format

The config file is JSON with the following structure:

```json
{
  "api_url": "http://localhost:8080",
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "email": "admin@example.com",
  "name": "admin",
  "etherion_bin": ""
}
```

### Fields

- **api_url** (string): The HTTP/HTTPS URL of the Etherion API server. Defaults to `http://localhost:8080` if not specified or empty.
- **access_token** (string): Your JWT token, obtained during login. The API rejects requests without a valid token.
- **email** (string): Your login email (informational, used by the TUI to show "logged in as...").
- **name** (string): Your display name (informational).
- **etherion_bin** (string, optional): Explicit path to the `etherion` CLI binary. Used only if the normal binary resolution fails.

## Config Loading and Defaults

When you start `etherion-tui`, the `config.Load()` function:

1. Creates a default config with `APIURL = "http://localhost:8080"`
2. Checks the environment variable `ETHERION_API_URL`; if set, overrides the default
3. Attempts to read `~/.config/etherion/tui.json`; if it exists, unmarshals it
4. If the file doesn't exist, returns the default config (no error)
5. If unmarshaling fails, returns an error (but the TUI continues with the default)

From `/tui/internal/config/config.go`:

```go
func Load() (*Config, error) {
    cfg := &Config{
        APIURL: "http://127.0.0.1:8080",
    }

    if v := os.Getenv("ETHERION_API_URL"); v != "" {
        cfg.APIURL = v
    }

    data, err := os.ReadFile(DefaultPath())
    if err != nil {
        if os.IsNotExist(err) {
            return cfg, nil
        }
        return cfg, err
    }

    if jsonErr := json.Unmarshal(data, cfg); jsonErr != nil {
        return cfg, jsonErr
    }

    if cfg.APIURL == "" {
        if v := os.Getenv("ETHERION_API_URL"); v != "" {
            cfg.APIURL = v
        } else {
            cfg.APIURL = "http://127.0.0.1:8080"
        }
    }

    return cfg, nil
}
```

This means:

- If you have no config file, the TUI starts with defaults (API URL = `localhost:8080`)
- If `ETHERION_API_URL` is set in your shell environment, it takes precedence over the config file
- If the config file is malformed JSON, an error is logged but the TUI continues

## Saving the Config

After a successful login, the TUI saves the updated config (with the new token and email) by calling `cfg.Save()`:

```go
func (c *Config) Save() error {
    path := DefaultPath()
    if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
        return err
    }
    data, err := json.MarshalIndent(c, "", "  ")
    if err != nil {
        return err
    }
    return os.WriteFile(path, data, 0o600)
}
```

Key details:

- Creates parent directories if they don't exist (with `0o700` = rwx for owner only)
- Writes the config file with `0o600` permissions (read/write for owner only, no access for others)
- Uses JSON indentation for readability

The permissions `0o600` are important: they ensure that your access token (which can impersonate you) is not readable by other users on the system.

## Environment Variable Overrides

### ETHERION_API_URL

Override the API server URL:

```bash
ETHERION_API_URL=http://192.168.1.100:8000 etherion-tui
```

This is useful if:
- Your API server is on a different host
- You're testing against a staging server
- You have multiple Etherion deployments and want to switch between them

The environment variable takes precedence over the config file.

### ETHERION_BIN

Specify an explicit path to the `etherion` CLI binary:

```bash
ETHERION_BIN=/opt/etherion/bin/etherion etherion-tui
```

This is useful if your `etherion` binary is in a non-standard location, or if you want to test a specific version.

## Binary Resolution

The TUI needs to locate the `etherion` CLI binary to run commands like `etherion bootstrap`, `etherion migrate`, and `etherion serve`. Binary resolution happens in this order:

1. **Config file override**: If `etherion_bin` is set in the config file and the file exists, use it.
2. **Environment variable**: If `ETHERION_BIN` is set and the file exists, use it.
3. **PATH lookup**: Try `exec.LookPath("etherion")` to find the binary in your `$PATH`.
4. **Alongside TUI binary**: Look in the same directory as the running `etherion-tui` binary (common when both are installed via pip).
5. **User local bin**: Check `~/.local/bin/etherion` (common for pip installations with `--user`).
6. **Failure**: If none of the above work, report an error.

From `/tui/internal/config/config.go`:

```go
func (c *Config) EtherionBin() (string, bool) {
    // 1. Explicit config override
    if c.EtherionBinOverride != "" {
        if _, err := os.Stat(c.EtherionBinOverride); err == nil {
            return c.EtherionBinOverride, true
        }
    }

    // 2. Env var override
    if v := os.Getenv("ETHERION_BIN"); v != "" {
        if _, err := os.Stat(v); err == nil {
            return v, true
        }
    }

    // 3. Standard PATH lookup
    if path, err := exec.LookPath("etherion"); err == nil {
        return path, true
    }

    // 4. Same directory as the TUI binary itself
    binName := "etherion"
    if runtime.GOOS == "windows" {
        binName = "etherion.exe"
    }
    if self, err := os.Executable(); err == nil {
        candidate := filepath.Join(filepath.Dir(self), binName)
        if _, err := os.Stat(candidate); err == nil {
            return candidate, true
        }
    }

    // 5. ~/.local/bin (common pip --user install location)
    if home, err := os.UserHomeDir(); err == nil {
        candidate := filepath.Join(home, ".local", "bin", binName)
        if _, err := os.Stat(candidate); err == nil {
            return candidate, true
        }
    }

    return "", false
}
```

## Cross-Platform Binary Selection

The TUI itself is distributed as precompiled binaries for multiple platforms. The Python wrapper (`etherion_tui/__init__.py`) detects your OS and architecture and runs the correct binary.

From `/tui-pkg/etherion_tui/__init__.py`:

```python
def _binary_name() -> str:
    system = platform.system()
    machine = platform.machine().lower()
    arch = "arm64" if machine in ("arm64", "aarch64") else "amd64"

    if system == "Windows":
        return f"etherion-tui-windows-{arch}.exe"
    if system == "Darwin":
        return f"etherion-tui-darwin-{arch}"
    return f"etherion-tui-linux-{arch}"


def main():
    bin_dir = os.path.join(os.path.dirname(__file__), "bin")
    binary = os.path.join(bin_dir, _binary_name())

    if not os.path.exists(binary):
        print(f"etherion-tui: no binary for your platform...")
        sys.exit(1)

    if platform.system() != "Windows":
        current = os.stat(binary).st_mode
        os.chmod(binary, current | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    if platform.system() == "Windows":
        sys.exit(subprocess.call([binary] + sys.argv[1:]))
    else:
        os.execv(binary, [binary] + sys.argv[1:])
```

This wrapper:

1. Detects your OS (`Windows`, `Darwin`, or Linux) and architecture (`amd64` or `arm64`)
2. Constructs the expected binary name (e.g., `etherion-tui-linux-amd64`)
3. Checks if the binary exists; if not, shows an error
4. On Unix, makes the binary executable (via `chmod`)
5. On Windows, uses `subprocess.call()` to run it
6. On Unix, uses `os.execv()` to replace the Python process with the binary (cleaner)

The binary is bundled inside the Python package at `etherion_tui/bin/etherion-tui-<os>-<arch>`. When you install the package, these binaries are included.

## Typical Workflows

### Single Server, Single User

You install `etherion-tui` and run it:

```bash
pip install etherion
etherion-tui
```

The TUI creates `~/.config/etherion/tui.json` after your first login. Every subsequent run uses the saved config (no need to re-login unless you delete the config).

### Multiple Servers

You have two Etherion deployments (production and staging). To switch:

```bash
# Connect to staging
ETHERION_API_URL=http://staging.etherion.internal:8000 etherion-tui

# Later, connect to production
ETHERION_API_URL=http://prod.etherion.internal:8000 etherion-tui
```

Each environment can have its own token and config. The environment variable overrides the saved config on a per-invocation basis.

### Non-Standard Install

Your `etherion` binary is in `/opt/etherion/bin/` instead of `$PATH`:

```bash
ETHERION_BIN=/opt/etherion/bin/etherion etherion-tui
```

Or add it to the config file once:

```json
{
  "api_url": "http://localhost:8080",
  "etherion_bin": "/opt/etherion/bin/etherion"
}
```

### Debugging Configuration

To see what config the TUI loaded:

1. Run `etherion-tui`
2. If you're not logged in, go to **Tab 1 (Connect)** and check the "Server" field—it shows the loaded API URL
3. If you're logged in, the Dashboard will show if the API is reachable (green check = good)

To manually inspect the config file:

```bash
cat ~/.config/etherion/tui.json
```

To reset (delete config and start fresh):

```bash
rm ~/.config/etherion/tui.json
etherion-tui
```

## Security Notes

- **Token Storage**: Your JWT token is stored in `~/.config/etherion/tui.json` with `0o600` permissions. Only you can read it.
- **Token Lifetime**: The token's lifetime is determined by the Etherion API server (typically 24 hours). After expiry, you'll need to re-login.
- **Token Revocation**: If you suspect your token is compromised, delete the config file and re-login. This generates a new token.
- **Environment Variables**: If you set `ETHERION_API_URL` or `ETHERION_BIN`, these are stored in your shell history. Be aware if sharing your terminal or scripts.

## Troubleshooting

### "etherion binary not found"

The TUI couldn't find the `etherion` CLI. Check:

1. Is `etherion` installed? Run `pip list | grep etherion`
2. Is it in your `$PATH`? Run `which etherion`
3. If installed with `pip --user`, is `~/.local/bin` in your `$PATH`? Run `echo $PATH | grep .local`

If all else fails, set `ETHERION_BIN` explicitly.

### "could not load config: ..."

The config file is malformed JSON. Check:

```bash
cat ~/.config/etherion/tui.json
```

If it's broken, delete it and re-login:

```bash
rm ~/.config/etherion/tui.json
etherion-tui
```

### API server not reachable

If the Dashboard shows API in red, check:

1. Is the API server running? (on the Setup wizard's last step)
2. Is the API URL correct? (default `localhost:8080`; override with `ETHERION_API_URL`)
3. Is there a firewall blocking the connection?

Verify connectivity manually:

```bash
nc -zv localhost 8000
```

(Replace `8000` with your API port.)

### Can't log in

1. Double-check your email and password
2. Is the server running and reachable? (Dashboard tab should show green API check)
3. Is the server URL correct? (shown in the Connect tab's "Server" field)

If all else fails, check the server logs:

```bash
journalctl -u etherion -n 50
# or if Docker:
docker-compose logs etherion
```
