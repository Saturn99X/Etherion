package ui

import (
	"fmt"
	"net"
	"os"
	"os/exec"
	"strings"
	"time"

	"github.com/charmbracelet/bubbles/textinput"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/etherion-ai/etherion/tui/internal/config"
	"github.com/etherion-ai/etherion/tui/internal/runner"
)

type setupStep int

const (
	sStepIdle      setupStep = iota
	sStepVerify              // 1 — etherion binary found?
	sStepCheckEnv            // 2 — .env exists?
	sStepBootstrap           // 3 — etherion bootstrap (Docker only)
	sStepMigrate             // 4 — etherion migrate
	sStepTenantForm          // 5 — collect email + password (inline form)
	sStepTenant              // 5 (running) — etherion tenant create EMAIL PASS
	sStepOAuth               // 6 — manual: connect OAuth providers
	sStepServe               // 7 — etherion serve (detached)
	sStepDone                // 8 — done
)

type setupMode int

const (
	setupModeDocker    setupMode = iota // docker compose up -d
	setupModeBareMetal                  // services already running via systemd
)

var setupStepLabels = []string{
	"Find etherion binary",
	"Check .env file",
	"Bootstrap services",
	"Run migrations",
	"Create admin account",
	"Connect OAuth",
	"Launch server",
	"Done!",
}

// setupDoneMsg carries the result of an async setup step.
type setupDoneMsg struct {
	extra string
	err   error
}

// SetupModel is the onboarding wizard.
type SetupModel struct {
	step         setupStep
	mode         setupMode // docker or bare-metal, chosen at sStepIdle
	modeCursor   int       // 0=Docker, 1=Bare-Metal (used only at sStepIdle)
	lines        []string
	running      bool
	lastFailed   bool // true when the last step ended with an error
	cfg          *config.Config
	width        int
	height       int
	scrollOffset int // 0 = follow bottom; N = N lines from bottom

	// tenant form (step 5)
	tenantInputs  [2]textinput.Model // [0]=email, [1]=password
	tenantFocused int
}

func NewSetupModel(cfg *config.Config) SetupModel {
	emailIn := textinput.New()
	emailIn.Placeholder = "admin@example.com"
	emailIn.CharLimit = 200
	emailIn.Focus()

	passIn := textinput.New()
	passIn.Placeholder = "choose a password"
	passIn.EchoMode = textinput.EchoPassword
	passIn.CharLimit = 200

	return SetupModel{
		step:         sStepIdle,
		cfg:          cfg,
		tenantInputs: [2]textinput.Model{emailIn, passIn},
	}
}

func (m SetupModel) Init() tea.Cmd { return nil }

func (m SetupModel) Update(msg tea.Msg) (SetupModel, tea.Cmd) {
	// --- tenant form input handling (step 5 waiting for user) ---
	if m.step == sStepTenantForm && !m.running {
		switch msg := msg.(type) {
		case tea.KeyMsg:
			switch msg.String() {
			case "tab", "down":
				m.tenantInputs[m.tenantFocused].Blur()
				m.tenantFocused = (m.tenantFocused + 1) % 2
				m.tenantInputs[m.tenantFocused].Focus()
				return m, textinput.Blink
			case "shift+tab", "up":
				m.tenantInputs[m.tenantFocused].Blur()
				m.tenantFocused = (m.tenantFocused - 1 + 2) % 2
				m.tenantInputs[m.tenantFocused].Focus()
				return m, textinput.Blink
			case "enter":
				if m.tenantFocused == 0 {
					// Advance to password field
					m.tenantInputs[0].Blur()
					m.tenantFocused = 1
					m.tenantInputs[1].Focus()
					return m, textinput.Blink
				}
				// Submit
				return m.runTenantCreate()
			default:
				var cmd tea.Cmd
				m.tenantInputs[m.tenantFocused], cmd = m.tenantInputs[m.tenantFocused].Update(msg)
				return m, cmd
			}
		default:
			// pass cursor blink etc through to focused input
			var cmd tea.Cmd
			m.tenantInputs[m.tenantFocused], cmd = m.tenantInputs[m.tenantFocused].Update(msg)
			return m, cmd
		}
	}

	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		m.width = msg.Width
		m.height = msg.Height

	case tea.KeyMsg:
		if m.running {
			return m, nil
		}
		switch msg.String() {
		case "enter":
			if m.step == sStepIdle {
				m.mode = setupMode(m.modeCursor)
			}
			if m.lastFailed {
				return m.retryCurrentStep()
			}
			return m.advance()
		case "left", "h":
			if m.step == sStepIdle {
				m.modeCursor = 0
			}
		case "right", "l":
			if m.step == sStepIdle {
				m.modeCursor = 1
			}
		case "up", "pgup":
			visible := m.logLinesVisible()
			by := 1
			if msg.String() == "pgup" {
				by = visible / 2
			}
			maxScroll := len(m.lines) - visible
			if maxScroll < 0 {
				maxScroll = 0
			}
			m.scrollOffset += by
			if m.scrollOffset > maxScroll {
				m.scrollOffset = maxScroll
			}
		case "down", "pgdown":
			by := 1
			if msg.String() == "pgdown" {
				by = m.logLinesVisible() / 2
			}
			m.scrollOffset -= by
			if m.scrollOffset < 0 {
				m.scrollOffset = 0
			}
		case "r":
			return NewSetupModel(m.cfg), nil
		}

	case lineMsg:
		if msg.tab == tabSetup {
			m.lines = append(m.lines, msg.line)
			m.scrollOffset = 0
		}

	case setupDoneMsg:
		m.running = false
		if msg.extra != "" {
			m.lines = append(m.lines, msg.extra) // always show command output
		}
		if msg.err != nil {
			m.lines = append(m.lines, StyleError.Render("✗ Error: "+msg.err.Error()))
			m.lines = append(m.lines, StyleWarning.Render("  Fix the issue, then press Enter to retry."))
			m.lastFailed = true
			m.scrollOffset = 0
			// do NOT change m.step — retryCurrentStep() handles re-running it
		} else {
			m.lastFailed = false
			m.lines = append(m.lines, StyleOK.Render(iconOK+" Done"))
			m.scrollOffset = 0
			return m.advance()
		}

	case cmdDoneMsg:
		if msg.tab == tabSetup {
			m.running = false
			if msg.err != nil {
				m.lines = append(m.lines, StyleError.Render("✗ Error: "+msg.err.Error()))
				m.lines = append(m.lines, StyleWarning.Render("  Fix the issue, then press Enter to retry."))
				m.lastFailed = true
				m.scrollOffset = 0
			} else {
				m.lastFailed = false
				m.lines = append(m.lines, StyleOK.Render(iconOK+" Done"))
				m.scrollOffset = 0
				return m.advance()
			}
		}
	}
	return m, nil
}

func (m SetupModel) advance() (SetupModel, tea.Cmd) {
	switch m.step {

	// ── Step 1: find etherion binary ─────────────────────────────────────────
	case sStepIdle:
		m.step = sStepVerify
		m.running = true
		m.lines = append(m.lines, StyleHeader.Render("Looking for etherion binary…"))
		cfg := m.cfg
		return m, func() tea.Msg {
			bin, ok := cfg.EtherionBin()
			if !ok {
				return setupDoneMsg{err: fmt.Errorf(
					"etherion not found in PATH or ~/.local/bin\n" +
						"  → run:  pip install etherion",
				)}
			}
			return setupDoneMsg{extra: StyleOK.Render("  Found: " + bin)}
		}

	// ── Step 2: check .env ────────────────────────────────────────────────────
	case sStepVerify:
		m.step = sStepCheckEnv
		m.running = true
		m.lines = append(m.lines, StyleHeader.Render("Checking for .env file…"))
		return m, func() tea.Msg {
			if _, err := os.Stat(".env"); os.IsNotExist(err) {
				return setupDoneMsg{err: fmt.Errorf(
					".env not found in current directory\n" +
						"  → run:  etherion init",
				)}
			}
			return setupDoneMsg{}
		}

	// ── Step 3: init then bootstrap ──────────────────────────────────────────
	case sStepCheckEnv:
		m.step = sStepBootstrap
		m.running = true
		if m.mode == setupModeBareMetal {
			m.lines = append(m.lines, StyleHeader.Render("Running: etherion init && etherion bootstrap --mode native"))
			m.lines = append(m.lines, StyleMuted.Render("  Polls PostgreSQL·Redis·MinIO every 2s (90s timeout)"))
			m.lines = append(m.lines, StyleMuted.Render("  Start services manually if they are not running yet:"))
			m.lines = append(m.lines, StyleMuted.Render("    sudo systemctl start postgresql redis minio"))
			return m, doInitThenBootstrap(m.cfg, "--mode", "native")
		}
		m.lines = append(m.lines, StyleHeader.Render("Running: etherion init && etherion bootstrap  (docker compose up -d)"))
		return m, doInitThenBootstrap(m.cfg)

	// ── Step 4: migrate ───────────────────────────────────────────────────────
	case sStepBootstrap:
		m.step = sStepMigrate
		m.running = true
		m.lines = append(m.lines, StyleHeader.Render("Running: etherion migrate"))
		return m, doEtherionCmd(m.cfg, "migrate")

	// ── Step 5a: show tenant form (collect email + password) ─────────────────
	case sStepMigrate:
		m.step = sStepTenantForm
		m.running = false
		m.tenantFocused = 0
		m.tenantInputs[0].Focus()
		m.lines = append(m.lines, StyleHeader.Render("Create your admin account:"))

	// ── Step 5b: tenant form submitted — run create ───────────────────────────
	// (this case is reached via runTenantCreate, not Enter key)

	// ── Step 6: OAuth (manual) ────────────────────────────────────────────────
	case sStepTenant:
		m.step = sStepOAuth
		m.running = false
		m.lines = append(m.lines, StyleWarning.Render(
			iconArrow+" Switch to tab 6 (OAuth) to connect providers, then press Enter",
		))

	// ── Step 7: start server detached ─────────────────────────────────────────
	case sStepOAuth:
		m.step = sStepServe
		m.running = true
		m.lines = append(m.lines, StyleHeader.Render("Starting: etherion serve (background)"))
		cfg := m.cfg
		return m, func() tea.Msg {
			bin, ok := cfg.EtherionBin()
			if !ok {
				return setupDoneMsg{err: fmt.Errorf("etherion binary not found")}
			}
			if err := runner.StartDetached(bin, []string{"serve"}, nil); err != nil {
				return setupDoneMsg{err: err}
			}
			return setupDoneMsg{extra: StyleMuted.Render("  Server starting in background…")}
		}

	// ── Done ──────────────────────────────────────────────────────────────────
	case sStepServe:
		m.step = sStepDone
		m.running = false
		m.lines = append(m.lines, StyleOK.Render(
			"✓ Platform is running!\n"+
				"  → Press 1 (Connect) to log in with the credentials you just created.\n"+
				"  → Press 8 for the Dashboard.",
		))
	}

	return m, nil
}

// retryCurrentStep re-runs whichever step last failed without advancing.
func (m SetupModel) retryCurrentStep() (SetupModel, tea.Cmd) {
	m.lastFailed = false
	switch m.step {
	case sStepVerify:
		m.running = true
		m.lines = append(m.lines, StyleHeader.Render("Retrying: find etherion binary…"))
		cfg := m.cfg
		return m, func() tea.Msg {
			bin, ok := cfg.EtherionBin()
			if !ok {
				return setupDoneMsg{err: fmt.Errorf("etherion not found in PATH or ~/.local/bin\n  → run:  pip install etherion")}
			}
			return setupDoneMsg{extra: StyleOK.Render("  Found: " + bin)}
		}
	case sStepCheckEnv:
		m.running = true
		m.lines = append(m.lines, StyleHeader.Render("Retrying: check .env file…"))
		return m, func() tea.Msg {
			if _, err := os.Stat(".env"); os.IsNotExist(err) {
				return setupDoneMsg{err: fmt.Errorf(".env not found\n  → run:  etherion init")}
			}
			return setupDoneMsg{}
		}
	case sStepBootstrap:
		m.running = true
		if m.mode == setupModeBareMetal {
			m.lines = append(m.lines, StyleHeader.Render("Retrying: etherion init && etherion bootstrap --mode native"))
			return m, doInitThenBootstrap(m.cfg, "--mode", "native")
		}
		m.lines = append(m.lines, StyleHeader.Render("Retrying: etherion init && etherion bootstrap"))
		return m, doInitThenBootstrap(m.cfg)
	case sStepMigrate:
		m.running = true
		m.lines = append(m.lines, StyleHeader.Render("Retrying: etherion migrate"))
		return m, doEtherionCmd(m.cfg, "migrate")
	case sStepTenant, sStepTenantForm:
		return m.runTenantCreate()
	case sStepServe:
		m.running = true
		m.lines = append(m.lines, StyleHeader.Render("Retrying: etherion serve (background)"))
		cfg := m.cfg
		return m, func() tea.Msg {
			bin, ok := cfg.EtherionBin()
			if !ok {
				return setupDoneMsg{err: fmt.Errorf("etherion binary not found")}
			}
			if err := runner.StartDetached(bin, []string{"serve"}, nil); err != nil {
				return setupDoneMsg{err: err}
			}
			return setupDoneMsg{extra: StyleMuted.Render("  Server starting in background…")}
		}
	}
	return m, nil
}

// runTenantCreate is called when the user submits the tenant form.
func (m SetupModel) runTenantCreate() (SetupModel, tea.Cmd) {
	email := strings.TrimSpace(m.tenantInputs[0].Value())
	password := m.tenantInputs[1].Value()

	if email == "" || password == "" {
		m.lines = append(m.lines, StyleError.Render("Email and password are required"))
		return m, nil
	}

	m.step = sStepTenant
	m.running = true
	m.lines = append(m.lines, StyleMuted.Render(fmt.Sprintf(
		"  Creating tenant for %s…", email,
	)))

	// Derive display name from the email local-part (e.g. "admin" from "admin@example.com").
	name := email
	if at := strings.Index(email, "@"); at > 0 {
		name = email[:at]
	}

	cfg := m.cfg
	return m, func() tea.Msg {
		bin, ok := cfg.EtherionBin()
		if !ok {
			return setupDoneMsg{err: fmt.Errorf("etherion binary not found")}
		}
		lines, err := runner.RunCommand(bin, []string{
			"create-tenant",
			"--email", email,
			"--password", password,
			"--name", name,
		}, nil)
		extra := ""
		if len(lines) > 0 {
			tail := lines
			if len(tail) > 5 {
				tail = tail[len(tail)-5:]
			}
			extra = StyleMuted.Render(strings.Join(tail, "\n"))
		}
		return setupDoneMsg{extra: extra, err: err}
	}
}

func (m SetupModel) View() string {
	var sb strings.Builder
	sb.WriteString(StyleHeader.Render("  Onboarding Setup") + "\n\n")

	// ── Mode selector (only at idle, before wizard starts) ───────────────────
	if m.step == sStepIdle {
		dockerBtn := StyleTabInactive.Render("  🐳 Docker Mode  ")
		bmBtn := StyleTabInactive.Render("  ⚙  Bare Metal Mode  ")
		if m.modeCursor == 0 {
			dockerBtn = StyleTabActive.Render("  🐳 Docker Mode  ")
		} else {
			bmBtn = StyleTabActive.Render("  ⚙  Bare Metal Mode  ")
		}
		sb.WriteString("  " + dockerBtn + "   " + bmBtn + "\n\n")

		if m.modeCursor == 0 {
			sb.WriteString("  " + StyleMuted.Render("Starts postgres, redis, minio via docker compose up -d") + "\n")
			sb.WriteString("  " + StyleMuted.Render("Requires: Docker installed and running") + "\n\n")
		} else {
			sb.WriteString("  " + StyleWarning.Render("Guided setup for bare metal / native installs") + "\n")
			sb.WriteString("  " + StyleMuted.Render("Checks PostgreSQL (5432) · Redis (6379) · MinIO (9000)") + "\n")
			sb.WriteString("  " + StyleMuted.Render("Tries 'systemctl start' for any service not running") + "\n")
			sb.WriteString("  " + StyleMuted.Render("Shows install instructions if a service is missing") + "\n\n")
		}

		sb.WriteString(StyleHelp.Render("  ←/→: select mode   Enter: confirm and start"))
		return sb.String()
	}

	// ── Mode badge (shown while wizard is running) ────────────────────────────
	if m.mode == setupModeDocker {
		sb.WriteString("  " + StyleTabInactive.Render(" Docker Mode ") + "\n\n")
	} else {
		sb.WriteString("  " + StyleTabInactive.Render(" Bare Metal Mode ") + "\n\n")
	}

	// ── Step progress list ────────────────────────────────────────────────────
	displayStep := m.step
	if displayStep >= sStepTenant {
		displayStep-- // collapse TenantForm+Tenant into one display slot
	}

	for i, label := range setupStepLabels {
		step := setupStep(i + 1)
		// In bare metal mode, step 3 label changes to service check.
		if m.mode == setupModeBareMetal && step == sStepBootstrap {
			bmLabel := "Check & start services  (PostgreSQL · Redis · MinIO)"
			prefix := "     "
			style := StyleMuted
			switch {
			case step < displayStep:
				prefix = "  " + StyleOK.Render(iconOK) + "  "
				style = StyleOK
			case step == displayStep:
				prefix = "  " + StyleWarning.Render(iconArrow) + "  "
				style = StyleWarning
			}
			sb.WriteString(prefix + style.Render(fmt.Sprintf("Step %d: %s", i+1, bmLabel)) + "\n")
			continue
		}
		prefix := "     "
		style := StyleMuted
		switch {
		case step < displayStep:
			prefix = "  " + StyleOK.Render(iconOK) + "  "
			style = StyleOK
		case step == displayStep:
			prefix = "  " + StyleWarning.Render(iconArrow) + "  "
			style = StyleWarning
		}
		sb.WriteString(prefix + style.Render(fmt.Sprintf("Step %d: %s", i+1, label)) + "\n")
	}
	sb.WriteString("\n")

	// ── Output log ────────────────────────────────────────────────────────────
	if len(m.lines) > 0 {
		visible := m.logLinesVisible()
		total := len(m.lines)
		end := total - m.scrollOffset
		if end < 0 {
			end = 0
		}
		start := end - visible
		if start < 0 {
			start = 0
		}
		displayed := m.lines[start:end]
		w := m.width - 8
		if w < 40 {
			w = 40
		}
		box := StyleBorder.Width(w).Render(strings.Join(displayed, "\n"))
		if m.scrollOffset > 0 {
			hint := StyleMuted.Render(fmt.Sprintf("  ↑ %d more lines  (↑↓ pgup/pgdn to scroll)", m.scrollOffset))
			sb.WriteString(hint + "\n")
		}
		sb.WriteString(box + "\n")
	}

	// ── Tenant form (shown inline when at sStepTenantForm) ───────────────────
	if m.step == sStepTenantForm && !m.running {
		labels := [2]string{"Email   ", "Password"}
		for i, label := range labels {
			style := StyleMuted
			if i == m.tenantFocused {
				style = StyleWarning
			}
			sb.WriteString("  " + style.Render(label) + "  " + m.tenantInputs[i].View() + "\n\n")
		}
		btn := StyleTabInactive.Render("  Create Account  ")
		if m.tenantFocused == 1 {
			btn = StyleTabActive.Render("  Create Account  ")
		}
		sb.WriteString("  " + btn + "\n\n")
	}

	// ── Help bar ──────────────────────────────────────────────────────────────
	if !m.running && m.step != sStepTenantForm {
		switch m.step {
		case sStepOAuth:
			sb.WriteString(StyleHelp.Render("Press Enter after connecting OAuth providers"))
		case sStepDone:
			// nothing
		default:
			if m.lastFailed {
				sb.WriteString(StyleError.Render("⚠  Step failed — fix the issue, then press Enter to retry"))
			} else {
				sb.WriteString(StyleHelp.Render("Press Enter to continue"))
			}
		}
		sb.WriteString("\n" + StyleHelp.Render("r: restart wizard"))
	}
	return sb.String()
}

// logLinesVisible returns how many log lines can fit in the current terminal.
func (m SetupModel) logLinesVisible() int {
	if m.height == 0 {
		return 15
	}
	// Fixed chrome: tab bar(2) + header(2) + mode badge(2) + steps(9) + margins(4) + help(2) ≈ 21
	h := m.height - 21
	if h < 5 {
		h = 5
	}
	if h > 40 {
		h = 40
	}
	return h
}

// doBareMetalCheck verifies PostgreSQL, Redis, and MinIO are reachable.
// For each service that is not reachable it tries `systemctl start <unit>`,
// waits, then re-checks. Returns a setupDoneMsg with a detailed status log.
func doBareMetalCheck() tea.Cmd {
	type svcDef struct {
		name    string
		addr    string
		units   []string // systemd unit names to try
		install string   // human-readable install hint
	}
	services := []svcDef{
		{
			name:  "PostgreSQL",
			addr:  "127.0.0.1:5432",
			units: []string{"postgresql", "postgresql.service", "postgres"},
			install: "  apt:    sudo apt install postgresql\n" +
				"  pacman: sudo pacman -S postgresql\n" +
				"  dnf:    sudo dnf install postgresql-server\n" +
				"  Then:   sudo postgresql-setup --initdb && sudo systemctl enable --now postgresql",
		},
		{
			name:  "Redis",
			addr:  "127.0.0.1:6379",
			units: []string{"redis", "redis.service", "redis-server"},
			install: "  apt:    sudo apt install redis-server\n" +
				"  pacman: sudo pacman -S redis\n" +
				"  dnf:    sudo dnf install redis\n" +
				"  Then:   sudo systemctl enable --now redis",
		},
		{
			name:  "MinIO",
			addr:  "127.0.0.1:9000",
			units: []string{"minio", "minio.service"},
			install: "  Download: https://dl.min.io/server/minio/release/linux-amd64/minio\n" +
				"  Install:  sudo install minio /usr/local/bin/\n" +
				"  Then create /etc/systemd/system/minio.service and run:\n" +
				"            sudo systemctl enable --now minio",
		},
	}

	tcpOK := func(addr string) bool {
		c, err := net.DialTimeout("tcp", addr, 2*time.Second)
		if err != nil {
			return false
		}
		c.Close()
		return true
	}

	tryStart := func(units []string) bool {
		for _, unit := range units {
			if err := exec.Command("systemctl", "start", unit).Run(); err == nil {
				return true
			}
		}
		return false
	}

	return func() tea.Msg {
		var lines []string
		var failed []string

		for _, svc := range services {
			if tcpOK(svc.addr) {
				lines = append(lines, StyleOK.Render(fmt.Sprintf("  ✓ %s reachable on %s", svc.name, svc.addr)))
				continue
			}

			lines = append(lines, StyleWarning.Render(fmt.Sprintf("  ○ %s not reachable — trying systemctl start…", svc.name)))
			started := tryStart(svc.units)
			if started {
				// Give the service a moment to come up.
				time.Sleep(4 * time.Second)
			}

			if tcpOK(svc.addr) {
				lines = append(lines, StyleOK.Render(fmt.Sprintf("  ✓ %s started successfully", svc.name)))
			} else {
				lines = append(lines, StyleError.Render(fmt.Sprintf("  ✗ %s still not reachable on %s", svc.name, svc.addr)))
				if !started {
					lines = append(lines, StyleMuted.Render("    systemctl start failed — service may not be installed"))
				} else {
					lines = append(lines, StyleMuted.Render(fmt.Sprintf("    Started but not listening on %s — check config / logs", svc.addr)))
					lines = append(lines, StyleMuted.Render(fmt.Sprintf("    journalctl -u %s -n 30", svc.units[0])))
				}
				lines = append(lines, StyleMuted.Render("    Install instructions:"))
				for _, il := range strings.Split(svc.install, "\n") {
					lines = append(lines, StyleMuted.Render(il))
				}
				failed = append(failed, svc.name)
			}
		}

		extra := strings.Join(lines, "\n")
		if len(failed) > 0 {
			return setupDoneMsg{
				extra: extra,
				err:   fmt.Errorf("%s not running — fix above, then press Enter to retry", strings.Join(failed, ", ")),
			}
		}
		return setupDoneMsg{extra: extra}
	}
}

// doInitThenBootstrap runs `etherion init` first (idempotent), then `etherion bootstrap [extra...]`.
// This ensures docker-compose.services.yml exists before bootstrap tries to use it.
func doInitThenBootstrap(cfg *config.Config, bootstrapArgs ...string) tea.Cmd {
	return func() tea.Msg {
		bin, ok := cfg.EtherionBin()
		if !ok {
			return setupDoneMsg{err: fmt.Errorf("etherion binary not found — run: pip install etherion")}
		}
		// Step 1: init (idempotent — skip errors about existing files)
		runner.RunCommand(bin, []string{"init"}, nil) //nolint:errcheck — init errors are non-fatal
		// Step 2: bootstrap
		args := append([]string{"bootstrap"}, bootstrapArgs...)
		lines, err := runner.RunCommand(bin, args, nil)
		extra := ""
		if len(lines) > 0 {
			tail := lines
			if len(tail) > 20 {
				tail = tail[len(tail)-20:]
			}
			extra = StyleMuted.Render(strings.Join(tail, "\n"))
		}
		return setupDoneMsg{extra: extra, err: err}
	}
}

// doEtherionCmd builds a Cmd that runs an etherion subcommand.
func doEtherionCmd(cfg *config.Config, args ...string) tea.Cmd {
	return func() tea.Msg {
		bin, ok := cfg.EtherionBin()
		if !ok {
			return setupDoneMsg{err: fmt.Errorf("etherion binary not found — run: pip install etherion")}
		}
		lines, err := runner.RunCommand(bin, args, nil)
		extra := ""
		if len(lines) > 0 {
			tail := lines
			if len(tail) > 20 {
				tail = tail[len(tail)-20:]
			}
			extra = StyleMuted.Render(strings.Join(tail, "\n"))
		}
		return setupDoneMsg{extra: extra, err: err}
	}
}
