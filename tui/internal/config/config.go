package config

import (
	"encoding/json"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
)

// Config holds TUI runtime configuration persisted to ~/.config/etherion/tui.json.
type Config struct {
	APIURL         string `json:"api_url"`
	AccessToken    string `json:"access_token"`
	UserEmail      string `json:"email"`
	UserName       string `json:"name"`
	EtherionBinOverride string `json:"etherion_bin,omitempty"` // manual override
}

// DefaultPath returns the canonical path for the config file.
func DefaultPath() string {
	home, _ := os.UserHomeDir()
	return filepath.Join(home, ".config", "etherion", "tui.json")
}

// Load reads the config from disk, falling back to environment variables.
// If the file does not exist, a default Config is returned (no error).
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

// Save persists the config to DefaultPath(), creating parent directories as needed.
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

// IsLoggedIn reports whether a JWT access token is present.
func (c *Config) IsLoggedIn() bool {
	return c.AccessToken != ""
}

// EtherionBin resolves the path to the `etherion` CLI executable.
// Resolution order:
//  1. Config file override (etherion_bin)
//  2. ETHERION_BIN env var
//  3. PATH lookup via exec.LookPath
//  4. Same directory as the running binary (pip installs both to the same bin/)
//  5. ~/.local/bin/etherion
//
// Returns ("", false) if the binary cannot be found.
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
	//    (pip installs both etherion and etherion-tui to the same bin/ dir)
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

	// 5. ~/.local/bin (common pip --user install location on Linux/macOS)
	if home, err := os.UserHomeDir(); err == nil {
		candidate := filepath.Join(home, ".local", "bin", binName)
		if _, err := os.Stat(candidate); err == nil {
			return candidate, true
		}
	}

	return "", false
}
