package runner

import (
	"bufio"
	"bytes"
	"os/exec"
)

// RunCommand runs a command synchronously and returns all combined stdout+stderr
// lines plus any exit error.
func RunCommand(name string, args []string, env []string) ([]string, error) {
	cmd := exec.Command(name, args...)
	if len(env) > 0 {
		cmd.Env = env
	}

	var buf bytes.Buffer
	cmd.Stdout = &buf
	cmd.Stderr = &buf

	if err := cmd.Run(); err != nil {
		return splitLines(buf.String()), err
	}

	return splitLines(buf.String()), nil
}

// RunCommandStream runs a command and sends stdout+stderr lines to output.
// The done channel receives the final error (nil on success).
func RunCommandStream(name string, args []string, env []string, output chan<- string, done chan<- error) {
	cmd := exec.Command(name, args...)
	if len(env) > 0 {
		cmd.Env = env
	}

	pipe, err := cmd.StdoutPipe()
	if err != nil {
		done <- err
		return
	}
	cmd.Stderr = cmd.Stdout

	if err := cmd.Start(); err != nil {
		done <- err
		return
	}

	scanner := bufio.NewScanner(pipe)
	for scanner.Scan() {
		output <- scanner.Text()
	}

	done <- cmd.Wait()
}

func splitLines(s string) []string {
	var lines []string
	scanner := bufio.NewScanner(bytes.NewBufferString(s))
	for scanner.Scan() {
		lines = append(lines, scanner.Text())
	}
	return lines
}
