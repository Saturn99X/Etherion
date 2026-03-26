//go:build windows

package runner

import "os/exec"

// StartDetached starts a process detached from the TUI on Windows.
// Windows uses CREATE_NEW_PROCESS_GROUP via the subprocess flags.
func StartDetached(name string, args []string, env []string) error {
	cmd := exec.Command(name, args...)
	if len(env) > 0 {
		cmd.Env = env
	}
	return cmd.Start()
}
