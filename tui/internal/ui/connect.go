package ui

import (
	"context"
	"fmt"
	"strings"

	"github.com/charmbracelet/bubbles/textinput"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/etherion-ai/etherion/tui/internal/api"
	"github.com/etherion-ai/etherion/tui/internal/config"
	"github.com/etherion-ai/etherion/tui/internal/runner"
)

type connectMode int

const (
	connectModeLogin    connectMode = iota
	connectModeRegister             // create first admin account
)

const (
	connectFieldServer = iota
	connectFieldEmail
	connectFieldPassword
	connectFieldCount
)

// ConnectModel is the login / register / server-select form.
type ConnectModel struct {
	mode    connectMode
	inputs  [connectFieldCount]textinput.Model
	focused int
	status  string
	loading bool
	cfg     *config.Config
}

func NewConnectModel(cfg *config.Config) ConnectModel {
	serverInput := textinput.New()
	serverInput.Placeholder = "http://127.0.0.1:8000"
	serverInput.SetValue(cfg.APIURL)
	serverInput.CharLimit = 200
	serverInput.Focus()

	emailInput := textinput.New()
	emailInput.Placeholder = "you@example.com"
	if cfg.UserEmail != "" {
		emailInput.SetValue(cfg.UserEmail)
	}
	emailInput.CharLimit = 200

	passwordInput := textinput.New()
	passwordInput.Placeholder = "••••••••"
	passwordInput.EchoMode = textinput.EchoPassword
	passwordInput.CharLimit = 200

	return ConnectModel{
		mode:    connectModeLogin,
		inputs:  [connectFieldCount]textinput.Model{serverInput, emailInput, passwordInput},
		focused: connectFieldServer,
		status:  "Welcome! Enter your credentials to log in.",
		cfg:     cfg,
	}
}

func (m ConnectModel) Init() tea.Cmd { return textinput.Blink }

func (m ConnectModel) Update(msg tea.Msg) (ConnectModel, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.KeyMsg:
		if m.loading {
			return m, nil
		}
		switch msg.String() {
		case "ctrl+r":
			// Toggle login ↔ register
			return m.toggleMode(), textinput.Blink

		case "tab", "down":
			m.inputs[m.focused].Blur()
			m.focused = (m.focused + 1) % connectFieldCount
			m.inputs[m.focused].Focus()
			return m, textinput.Blink

		case "shift+tab", "up":
			m.inputs[m.focused].Blur()
			m.focused = (m.focused - 1 + connectFieldCount) % connectFieldCount
			m.inputs[m.focused].Focus()
			return m, textinput.Blink

		case "enter":
			if m.focused < connectFieldPassword {
				m.inputs[m.focused].Blur()
				m.focused++
				m.inputs[m.focused].Focus()
				return m, textinput.Blink
			}
			if m.mode == connectModeRegister {
				return m, m.doRegister()
			}
			return m, m.doLogin()

		default:
			var cmd tea.Cmd
			m.inputs[m.focused], cmd = m.inputs[m.focused].Update(msg)
			return m, cmd
		}

	case loginResultMsg:
		m.loading = false
		if msg.err != nil {
			m.status = StyleError.Render("Login failed: " + msg.err.Error())
		} else {
			m.status = StyleOK.Render("Logged in as " + msg.email)
		}
		return m, nil

	case registerResultMsg:
		m.loading = false
		if msg.err != nil {
			m.status = StyleError.Render("Registration failed: " + msg.err.Error())
		} else {
			m.status = StyleOK.Render(
				"✓ Account created! Now press Enter to log in.",
			)
			// Switch to login mode with credentials pre-filled.
			m.mode = connectModeLogin
		}
		return m, nil
	}

	var cmd tea.Cmd
	m.inputs[m.focused], cmd = m.inputs[m.focused].Update(msg)
	return m, cmd
}

func (m ConnectModel) toggleMode() ConnectModel {
	if m.mode == connectModeLogin {
		m.mode = connectModeRegister
		m.status = StyleWarning.Render(
			"Register mode: creates your first admin tenant.\n" +
				"  The server does NOT need to be running for this step.",
		)
	} else {
		m.mode = connectModeLogin
		m.status = "Enter your credentials to log in."
	}
	return m
}

func (m *ConnectModel) doLogin() tea.Cmd {
	server := strings.TrimSpace(m.inputs[connectFieldServer].Value())
	email := strings.TrimSpace(m.inputs[connectFieldEmail].Value())
	password := m.inputs[connectFieldPassword].Value()

	if server == "" {
		server = "http://127.0.0.1:8000"
	}
	if email == "" || password == "" {
		m.status = StyleError.Render("Email and password are required")
		return nil
	}

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

func (m *ConnectModel) doRegister() tea.Cmd {
	email := strings.TrimSpace(m.inputs[connectFieldEmail].Value())
	password := m.inputs[connectFieldPassword].Value()

	if email == "" || password == "" {
		m.status = StyleError.Render("Email and password are required")
		return nil
	}

	m.loading = true
	m.status = StyleMuted.Render("Creating account…")
	cfg := m.cfg

	return func() tea.Msg {
		bin, ok := cfg.EtherionBin()
		if !ok {
			return registerResultMsg{err: fmt.Errorf(
				"etherion binary not found — run: pip install etherion",
			)}
		}
		name := email
		if at := strings.Index(email, "@"); at > 0 {
			name = email[:at]
		}
		lines, err := runner.RunCommand(bin, []string{
			"create-tenant",
			"--email", email,
			"--password", password,
			"--name", name,
		}, nil)
		if err != nil {
			detail := err.Error()
			if len(lines) > 0 {
				tail := lines
				if len(tail) > 6 {
					tail = tail[len(tail)-6:]
				}
				detail = strings.Join(tail, " | ") + " (" + err.Error() + ")"
			}
			return registerResultMsg{err: fmt.Errorf("%s", detail)}
		}
		return registerResultMsg{email: email}
	}
}

func (m ConnectModel) View() string {
	var sb strings.Builder

	sb.WriteString(StyleHeader.Render("  Etherion AI Platform") + "\n\n")

	// ── Mode toggle — always visible ─────────────────────────────────────────
	loginBtn := StyleTabInactive.Render("  Login  ")
	regBtn := StyleTabInactive.Render("  Register (first time?)  ")
	if m.mode == connectModeLogin {
		loginBtn = StyleTabActive.Render("  Login  ")
	} else {
		regBtn = StyleTabActive.Render("  Register (first time?)  ")
	}
	sb.WriteString("  " + loginBtn + "  " + regBtn + "\n")
	sb.WriteString("  " + StyleMuted.Render("                                 ↑ Ctrl+R to switch") + "\n\n")

	// ── Register hint ─────────────────────────────────────────────────────────
	if m.mode == connectModeRegister {
		sb.WriteString("  " + StyleWarning.Render("Register mode: creates your first admin account.") + "\n")
		sb.WriteString("  " + StyleMuted.Render("The server does NOT need to be running for this step.") + "\n\n")
	}

	// ── Form fields ───────────────────────────────────────────────────────────
	labels := [connectFieldCount]string{"Server  ", "Email   ", "Password"}
	for i, label := range labels {
		style := StyleMuted
		if i == m.focused {
			style = StyleWarning
		}
		sb.WriteString("  " + style.Render(label) + "  " + m.inputs[i].View() + "\n\n")
	}

	// ── Submit button ─────────────────────────────────────────────────────────
	var btnLabel string
	if m.mode == connectModeRegister {
		btnLabel = "  Create Account  "
	} else {
		btnLabel = "  Login  "
	}
	btn := StyleTabInactive.Render(btnLabel)
	if m.focused == connectFieldPassword {
		btn = StyleTabActive.Render(btnLabel)
	}
	sb.WriteString("  " + btn + "\n\n")
	sb.WriteString("  Status: " + m.status + "\n")

	if m.cfg.IsLoggedIn() {
		sb.WriteString("\n  " + StyleOK.Render("Currently logged in as "+m.cfg.UserEmail) + "\n")
	}

	sb.WriteString("\n" + StyleHelp.Render("  Tab/↑↓: move  Enter: next/confirm  Ctrl+R: switch mode  Esc: back to Dashboard"))
	return sb.String()
}
