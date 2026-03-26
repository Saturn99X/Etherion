//go:build !windows

package runner

import (
	"os/exec"
	"syscall"
)

// StartDetached starts a long-running process detached from the TUI process group
// so it keeps running after the TUI exits.
func StartDetached(name string, args []string, env []string) error {
	cmd := exec.Command(name, args...)
	if len(env) > 0 {
		cmd.Env = env
	}
	cmd.SysProcAttr = &syscall.SysProcAttr{Setsid: true}
	return cmd.Start()
}
