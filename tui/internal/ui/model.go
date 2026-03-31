package ui

import (
	"fmt"
	"strings"
	"time"

	"github.com/charmbracelet/bubbles/key"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
	"github.com/etherion-ai/etherion/tui/internal/api"
	"github.com/etherion-ai/etherion/tui/internal/config"
)

const (
	tabConnect   = iota // 0 - Login
	tabSetup            // 1 - Onboarding wizard
	tabChat             // 2 - Threads + messages
	tabAgents           // 3 - Agent teams
	tabMonitor          // 4 - Job history
	tabOAuth            // 5 - OAuth connections
	tabLogs             // 6 - Scrollable logs
	tabDashboard        // 7 - Health dashboard
	tabKB               // 8 - Knowledge base sources
	tabCount            // 9
)

var tabNames = [tabCount]string{
	"Connect", "Setup", "Chat", "Agents", "Monitor", "OAuth", "Logs", "Dashboard", "KB",
}

// RootModel is the top-level Bubble Tea model.
type RootModel struct {
	activeTab int
	width     int
	height    int

	cfg *config.Config
	api *api.Client // nil until logged in

	connect   ConnectModel
	setup     SetupModel
	chat      ChatModel
	agents    AgentsModel
	monitor   MonitorModel
	oauth     OAuthModel
	logs      LogsModel
	dashboard DashboardModel
	kb        KBModel
}

// NewRootModel builds the initial model, loading config and deciding which tab to show first.
func NewRootModel(cfg *config.Config) RootModel {
	var apiClient *api.Client
	startTab := tabConnect

	if cfg.IsLoggedIn() {
		apiClient = api.New(cfg.APIURL, cfg.AccessToken)
		startTab = tabDashboard
	}

	m := RootModel{
		activeTab: startTab,
		cfg:       cfg,
		api:       apiClient,
		connect:   NewConnectModel(cfg),
		setup:     NewSetupModel(cfg),
		chat:      NewChatModel(apiClient),
		agents:    NewAgentsModel(apiClient),
		monitor:   NewMonitorModel(apiClient),
		oauth:     NewOAuthModel(apiClient),
		logs:      NewLogsModel(),
		dashboard: NewDashboardModel(),
		kb:        NewKBModel(apiClient),
	}
	return m
}

func (m RootModel) Init() tea.Cmd {
	cmds := []tea.Cmd{
		m.dashboard.Init(),
		tickEvery(3 * time.Second),
	}
	// If already logged in (token loaded from config), pre-fetch data.
	if m.api != nil {
		cmds = append(cmds,
			m.chat.loadThreads(),
			m.agents.loadTeams(),
			m.monitor.loadJobs(),
			m.kb.loadSources(),
		)
	}
	return tea.Batch(cmds...)
}

func tickEvery(d time.Duration) tea.Cmd {
	return tea.Tick(d, func(t time.Time) tea.Msg { return tickMsg{t} })
}

// isEditingText returns true when the active tab is handling keys itself,
// meaning global shortcuts (1-9 tab switch, q quit) must not fire.
func (m RootModel) isEditingText() bool {
	switch m.activeTab {
	case tabConnect:
		// Always has focused text inputs.
		return true
	case tabSetup:
		// Only block while the tenant email/password form is open.
		// All other Setup states (idle, running wizard, OAuth step, done) should
		// allow number-key tab switching — the wizard itself tells users to press 6.
		return m.setup.step == sStepTenantForm && !m.setup.running
	case tabAgents:
		return m.agents.mode == agentModeCreate || m.agents.mode == agentModeTools
	case tabOAuth:
		// Block in every state except the plain list: token input, shop domain
		// input, setup guide (q = go back, not quit), and browser-wait (esc = cancel).
		return m.oauth.state != oauthStateList
	}
	return false
}

func (m RootModel) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	var cmds []tea.Cmd

	switch msg := msg.(type) {
	// ---- global key bindings ------------------------------------------------
	case tea.KeyMsg:
		switch {
		case key.Matches(msg, key.NewBinding(key.WithKeys("ctrl+c"))):
			return m, tea.Quit
		// Escape always exits Connect tab back to Dashboard (escape hatch when
		// the user lands on the form without meaning to).
		case key.Matches(msg, key.NewBinding(key.WithKeys("esc"))):
			if m.activeTab == tabConnect && !m.connect.loading {
				m.activeTab = tabDashboard
				return m, nil
			}
		// 'q' quits only when not in a text-input tab
		case key.Matches(msg, key.NewBinding(key.WithKeys("q"))):
			if !m.isEditingText() {
				return m, tea.Quit
			}
		case key.Matches(msg, key.NewBinding(key.WithKeys("1"))):
			if !m.isEditingText() {
				m.activeTab = tabConnect
				return m, nil
			}
		case key.Matches(msg, key.NewBinding(key.WithKeys("2"))):
			if !m.isEditingText() {
				m.activeTab = tabSetup
				return m, nil
			}
		case key.Matches(msg, key.NewBinding(key.WithKeys("3"))):
			if !m.isEditingText() {
				m.activeTab = tabChat
				return m, nil
			}
		case key.Matches(msg, key.NewBinding(key.WithKeys("4"))):
			if !m.isEditingText() {
				m.activeTab = tabAgents
				return m, nil
			}
		case key.Matches(msg, key.NewBinding(key.WithKeys("5"))):
			if !m.isEditingText() {
				m.activeTab = tabMonitor
				return m, nil
			}
		case key.Matches(msg, key.NewBinding(key.WithKeys("6"))):
			if !m.isEditingText() {
				m.activeTab = tabOAuth
				return m, nil
			}
		case key.Matches(msg, key.NewBinding(key.WithKeys("7"))):
			if !m.isEditingText() {
				m.activeTab = tabLogs
				return m, nil
			}
		case key.Matches(msg, key.NewBinding(key.WithKeys("8"))):
			if !m.isEditingText() {
				m.activeTab = tabDashboard
				return m, nil
			}
		case key.Matches(msg, key.NewBinding(key.WithKeys("9"))):
			if !m.isEditingText() {
				m.activeTab = tabKB
				return m, nil
			}
		case key.Matches(msg, key.NewBinding(key.WithKeys("tab"))):
			if m.isEditingText() {
				break // let the active tab handle tab for field navigation
			}
			m.activeTab = (m.activeTab + 1) % tabCount
			return m, nil
		case key.Matches(msg, key.NewBinding(key.WithKeys("shift+tab"))):
			if m.isEditingText() {
				break
			}
			m.activeTab = (m.activeTab - 1 + tabCount) % tabCount
			return m, nil
		}

	// ---- window resize ------------------------------------------------------
	case tea.WindowSizeMsg:
		m.width = msg.Width
		m.height = msg.Height
		m.logs.SetSize(msg.Width, msg.Height-5)
		var c tea.Cmd
		m.setup, c = m.setup.Update(msg)
		cmds = append(cmds, c)

	// ---- ticker -------------------------------------------------------------
	case tickMsg:
		cmds = append(cmds, tickEvery(3*time.Second))
		if m.activeTab == tabDashboard {
			cmds = append(cmds, doHealthCheck(m.dashboard.env))
		}

	// ---- subprocess output --------------------------------------------------
	case lineMsg:
		m.logs, _ = m.logs.Update(logAppendMsg{line: msg.line})
		if msg.tab == tabSetup {
			var c tea.Cmd
			m.setup, c = m.setup.Update(msg)
			cmds = append(cmds, c)
		}

	case cmdDoneMsg:
		if msg.tab == tabSetup {
			var c tea.Cmd
			m.setup, c = m.setup.Update(msg)
			cmds = append(cmds, c)
		}

	// setupDoneMsg — exclusively for Setup tab; return immediately to prevent
	// the delegate section below from processing it a second time.
	case setupDoneMsg:
		var c tea.Cmd
		m.setup, c = m.setup.Update(msg)
		cmds = append(cmds, c)
		return m, tea.Batch(cmds...)

	// ---- health check -------------------------------------------------------
	case healthResultMsg:
		var c tea.Cmd
		m.dashboard, c = m.dashboard.Update(msg)
		cmds = append(cmds, c)
		return m, tea.Batch(cmds...)

	// ---- register result ----------------------------------------------------
	case registerResultMsg:
		var c tea.Cmd
		m.connect, c = m.connect.Update(msg)
		cmds = append(cmds, c)
		return m, tea.Batch(cmds...)

	// ---- login result -------------------------------------------------------
	case loginResultMsg:
		var c tea.Cmd
		m.connect, c = m.connect.Update(msg)
		cmds = append(cmds, c)
		if msg.err == nil {
			m.cfg.AccessToken = msg.token
			m.cfg.UserEmail = msg.email
			m.cfg.UserName = msg.name
			_ = m.cfg.Save()
			m.api = api.New(m.cfg.APIURL, msg.token)
			// Wire apiClient into all data-fetching tabs.
			m.oauth = NewOAuthModel(m.api)
			m.chat = NewChatModel(m.api)
			m.agents = NewAgentsModel(m.api)
			m.monitor = NewMonitorModel(m.api)
			m.kb = NewKBModel(m.api)
			// Kick off initial data loads.
			cmds = append(cmds, m.chat.loadThreads())
			cmds = append(cmds, m.agents.loadTeams())
			cmds = append(cmds, m.monitor.loadJobs())
			cmds = append(cmds, m.kb.loadSources())
			m.activeTab = tabDashboard
			cmds = append(cmds, doHealthCheck(m.dashboard.env))
		}
		return m, tea.Batch(cmds...)

	// ---- OAuth messages -----------------------------------------------------
	case oauthStatusMsg, oauthFlowStartedMsg, personalTokenSavedMsg, oauthRevokedMsg:
		var c tea.Cmd
		m.oauth, c = m.oauth.Update(msg)
		cmds = append(cmds, c)
		return m, tea.Batch(cmds...)

	// ---- GraphQL results ----------------------------------------------------
	case graphqlResultMsg:
		switch msg.tab {
		case tabChat:
			var c tea.Cmd
			m.chat, c = m.chat.Update(msg)
			cmds = append(cmds, c)
		case tabAgents:
			var c tea.Cmd
			m.agents, c = m.agents.Update(msg)
			cmds = append(cmds, c)
		case tabMonitor:
			var c tea.Cmd
			m.monitor, c = m.monitor.Update(msg)
			cmds = append(cmds, c)
		case tabKB:
			var c tea.Cmd
			m.kb, c = m.kb.Update(msg)
			cmds = append(cmds, c)
		}
		return m, tea.Batch(cmds...)
	}

	// ---- delegate to active tab ---------------------------------------------
	switch m.activeTab {
	case tabConnect:
		var c tea.Cmd
		m.connect, c = m.connect.Update(msg)
		cmds = append(cmds, c)
	case tabSetup:
		var c tea.Cmd
		m.setup, c = m.setup.Update(msg)
		cmds = append(cmds, c)
	case tabChat:
		var c tea.Cmd
		m.chat, c = m.chat.Update(msg)
		cmds = append(cmds, c)
	case tabAgents:
		var c tea.Cmd
		m.agents, c = m.agents.Update(msg)
		cmds = append(cmds, c)
	case tabMonitor:
		var c tea.Cmd
		m.monitor, c = m.monitor.Update(msg)
		cmds = append(cmds, c)
	case tabOAuth:
		var c tea.Cmd
		m.oauth, c = m.oauth.Update(msg)
		cmds = append(cmds, c)
	case tabLogs:
		var c tea.Cmd
		m.logs, c = m.logs.Update(msg)
		cmds = append(cmds, c)
	case tabDashboard:
		var c tea.Cmd
		m.dashboard, c = m.dashboard.Update(msg)
		cmds = append(cmds, c)
	case tabKB:
		var c tea.Cmd
		m.kb, c = m.kb.Update(msg)
		cmds = append(cmds, c)
	}

	return m, tea.Batch(cmds...)
}

func (m RootModel) View() string {
	return lipgloss.JoinVertical(lipgloss.Left,
		m.renderTabBar(),
		m.renderActiveTab(),
		m.renderHelp(),
	)
}

func (m RootModel) renderTabBar() string {
	if m.width < 40 {
		return StyleMuted.Render(fmt.Sprintf("[%d]", m.activeTab+1))
	}
	tabs := make([]string, tabCount)
	for i, name := range tabNames {
		label := fmt.Sprintf(" %d:%s ", i+1, name)
		if i == m.activeTab {
			tabs[i] = StyleTabActive.Render(label)
		} else {
			tabs[i] = StyleTabInactive.Render(label)
		}
	}
	bar := strings.Join(tabs, "")
	return StyleTabBar.Width(m.width).Render(bar)
}

func (m RootModel) renderActiveTab() string {
	switch m.activeTab {
	case tabConnect:
		return m.connect.View()
	case tabSetup:
		return m.setup.View()
	case tabChat:
		return m.chat.View()
	case tabAgents:
		return m.agents.View()
	case tabMonitor:
		return m.monitor.View()
	case tabOAuth:
		return m.oauth.View()
	case tabLogs:
		return m.logs.View()
	case tabDashboard:
		return m.dashboard.View()
	case tabKB:
		return m.kb.View()
	}
	return ""
}

func (m RootModel) renderHelp() string {
	return StyleHelp.Render("1-9: switch tabs  tab/shift+tab: cycle  ctrl+c: quit")
}
