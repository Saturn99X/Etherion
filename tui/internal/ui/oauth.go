package ui

import (
	"context"
	"fmt"
	"os/exec"
	"runtime"
	"strings"
	"time"

	"github.com/charmbracelet/bubbles/spinner"
	"github.com/charmbracelet/bubbles/textinput"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
	"github.com/etherion-ai/etherion/tui/internal/api"
)

// ---------------------------------------------------------------------------
// Provider metadata
// ---------------------------------------------------------------------------

// OAuthProvider describes how a provider is connected.
type OAuthProvider struct {
	ID          string
	Name        string
	AuthMethod  string   // "browser", "token", "token+extra", "browser+shop"
	TokenLabel  string   // label for manual-token input
	ExtraFields []string // additional fields required besides the token
	Description string
	TokenHelp   string // step-by-step instructions
	EnvVars     string // env vars the operator must set (browser flows only)
}

var providers = []OAuthProvider{
	// ── Token-based ──────────────────────────────────────────────────────
	{
		ID:          "github",
		Name:        "GitHub",
		AuthMethod:  "token",
		TokenLabel:  "Personal Access Token",
		Description: "Repos, issues, pull requests, code search",
		TokenHelp: "1. github.com → Settings → Developer settings\n" +
			"   → Personal access tokens → Tokens (classic)\n" +
			"2. 'Generate new token (classic)'\n" +
			"3. Scopes: repo, read:org, read:user\n" +
			"4. Copy token and paste below",
	},
	{
		ID:          "notion",
		Name:        "Notion",
		AuthMethod:  "token",
		TokenLabel:  "Integration Secret",
		Description: "Pages, databases, blocks",
		TokenHelp: "1. notion.so/profile/integrations\n" +
			"2. '+ New Integration' → type: Internal\n" +
			"3. Copy the Internal Integration Secret\n" +
			"4. In Notion: each page → '...' → Add Connections → your integration",
	},
	{
		ID:          "jira",
		Name:        "Jira",
		AuthMethod:  "token+extra",
		TokenLabel:  "API Token",
		ExtraFields: []string{"email", "domain"},
		Description: "Issues, projects, sprints (Atlassian)",
		TokenHelp: "1. id.atlassian.com/manage-profile/security/api-tokens\n" +
			"2. 'Create API token' → name it → Create\n" +
			"3. Copy the token (shown once only)\n" +
			"4. Email = your Atlassian account email\n" +
			"5. Domain = yourcompany.atlassian.net",
	},
	{
		ID:          "hubspot",
		Name:        "HubSpot",
		AuthMethod:  "token",
		TokenLabel:  "Private App Token",
		Description: "CRM contacts, companies, deals",
		TokenHelp: "1. HubSpot → Settings (⚙) → Integrations → Private Apps\n" +
			"2. 'Create a private app' → fill name\n" +
			"3. Scopes: crm.objects.contacts.read, crm.objects.companies.read\n" +
			"4. 'Create app' → Auth tab → copy the access token",
	},
	{
		ID:          "linear",
		Name:        "Linear",
		AuthMethod:  "token",
		TokenLabel:  "Personal API Key",
		Description: "Issues, projects, cycles, teams",
		TokenHelp: "1. linear.app/settings/account/security\n" +
			"2. Scroll to 'API keys' → 'Create key'\n" +
			"3. Give it a label → copy the key\n" +
			"   (No 'Bearer' prefix needed — platform handles it)",
	},

	// ── Browser OAuth (operator registers app with the provider) ─────────
	{
		ID:          "google",
		Name:        "Google",
		AuthMethod:  "browser",
		Description: "Google Drive, Gmail read access",
		EnvVars:     "OAUTH_GOOGLE_CLIENT_ID + OAUTH_GOOGLE_CLIENT_SECRET",
		TokenHelp: "Register a Google OAuth 2.0 App:\n" +
			"1. console.cloud.google.com/auth/clients\n" +
			"2. 'Create Client' → Web application\n" +
			"3. Authorized redirect URI:\n" +
			"   {YOUR_API_URL}/oauth/silo/google/callback\n" +
			"4. Copy Client ID + Secret → .env:\n" +
			"   OAUTH_GOOGLE_CLIENT_ID=...\n" +
			"   OAUTH_GOOGLE_CLIENT_SECRET=...\n" +
			"5. Restart server, then press Enter here",
	},
	{
		ID:          "slack",
		Name:        "Slack",
		AuthMethod:  "browser",
		Description: "Channels, messages, files",
		EnvVars:     "SLACK_USER_OAUTH_CLIENT_ID + SLACK_USER_OAUTH_CLIENT_SECRET",
		TokenHelp: "Register a Slack App:\n" +
			"1. api.slack.com/apps → 'Create New App' → From scratch\n" +
			"2. OAuth & Permissions → Redirect URLs:\n" +
			"   {YOUR_API_URL}/oauth/silo/slack/callback\n" +
			"3. User Token Scopes:\n" +
			"   channels:read, channels:history, files:read, users:read\n" +
			"4. Basic Information → App Credentials → .env:\n" +
			"   SLACK_USER_OAUTH_CLIENT_ID=...\n" +
			"   SLACK_USER_OAUTH_CLIENT_SECRET=...\n" +
			"5. Restart server, then press Enter here",
	},
	{
		ID:          "microsoft",
		Name:        "Microsoft 365",
		AuthMethod:  "browser",
		Description: "Outlook mail, OneDrive files",
		EnvVars:     "MICROSOFT_OAUTH_CLIENT_ID + MICROSOFT_OAUTH_CLIENT_SECRET",
		TokenHelp: "Register an Azure AD App:\n" +
			"1. entra.microsoft.com → App registrations → New registration\n" +
			"2. Redirect URI (Web):\n" +
			"   {YOUR_API_URL}/oauth/silo/microsoft/callback\n" +
			"3. API permissions → Add:\n" +
			"   Mail.Read, Files.Read, User.Read, offline_access\n" +
			"4. Certificates & secrets → New client secret → copy value\n" +
			"5. Overview page → copy Application (client) ID → .env:\n" +
			"   MICROSOFT_OAUTH_CLIENT_ID=...\n" +
			"   MICROSOFT_OAUTH_CLIENT_SECRET=...\n" +
			"6. Restart server, then press Enter here",
	},
	{
		ID:          "shopify",
		Name:        "Shopify",
		AuthMethod:  "browser+shop",
		Description: "Products, orders, customers",
		EnvVars:     "SHOPIFY_OAUTH_CLIENT_ID + SHOPIFY_OAUTH_CLIENT_SECRET",
		TokenHelp: "Register a Shopify App:\n" +
			"Partner App: partners.shopify.com → Apps → Create app\n" +
			"Custom App:  {store}.myshopify.com/admin/settings/apps → Develop apps\n" +
			"1. Allowed redirect URL:\n" +
			"   {YOUR_API_URL}/oauth/silo/shopify/callback\n" +
			"2. Scopes: read_products, read_orders, read_customers\n" +
			"3. Copy API key + API secret key → .env:\n" +
			"   SHOPIFY_OAUTH_CLIENT_ID=...\n" +
			"   SHOPIFY_OAUTH_CLIENT_SECRET=...\n" +
			"4. Restart server, then press Enter here",
	},
}

// providerStatus tracks real-time connection status from the API.
type providerStatus struct {
	connected bool
	checked   bool
}

// ---------------------------------------------------------------------------
// OAuthModel states
// ---------------------------------------------------------------------------

type oauthState int

const (
	oauthStateList       oauthState = iota
	oauthStateTokenInput            // entering personal token (+ extra fields)
	oauthStateSetupGuide            // show env var setup before browser flow
	oauthStateBrowserWait           // browser opened, polling
	oauthStateShopInput             // entering shop domain (Shopify only)
)

// OAuthModel manages the OAuth tab.
type OAuthModel struct {
	cursor   int
	state    oauthState
	statuses map[string]providerStatus

	tokenInputs  []textinput.Model
	tokenFocused int
	tokenErr     string

	shopInput textinput.Model

	authorizeURL string
	spinner      spinner.Model
	statusMsg    string

	apiClient *api.Client
}

func NewOAuthModel(client *api.Client) OAuthModel {
	sp := spinner.New()
	sp.Spinner = spinner.Dot
	sp.Style = StyleWarning

	shopIn := textinput.New()
	shopIn.Placeholder = "your-store.myshopify.com"
	shopIn.CharLimit = 100

	return OAuthModel{
		statuses:  make(map[string]providerStatus),
		spinner:   sp,
		shopInput: shopIn,
		apiClient: client,
	}
}

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------

func (m OAuthModel) Init() tea.Cmd {
	if m.apiClient == nil {
		return nil
	}
	cmds := make([]tea.Cmd, len(providers))
	for i, p := range providers {
		cmds[i] = doCheckOAuthStatus(m.apiClient, p.ID)
	}
	return tea.Batch(cmds...)
}

// ---------------------------------------------------------------------------
// Update
// ---------------------------------------------------------------------------

func (m OAuthModel) Update(msg tea.Msg) (OAuthModel, tea.Cmd) {
	var cmds []tea.Cmd

	switch msg := msg.(type) {

	case spinner.TickMsg:
		var c tea.Cmd
		m.spinner, c = m.spinner.Update(msg)
		cmds = append(cmds, c)

	case oauthStatusMsg:
		if msg.err == nil {
			m.statuses[msg.provider] = providerStatus{connected: msg.connected, checked: true}
		} else {
			m.statuses[msg.provider] = providerStatus{connected: false, checked: true}
		}
		if m.state == oauthStateBrowserWait && providers[m.cursor].ID == msg.provider {
			if msg.connected {
				m.state = oauthStateList
				m.statusMsg = StyleOK.Render(providers[m.cursor].Name + " connected!")
			} else {
				cmds = append(cmds, tea.Tick(2*time.Second, func(_ time.Time) tea.Msg {
					return doCheckOAuthStatus(m.apiClient, providers[m.cursor].ID)()
				}))
			}
		}

	case oauthFlowStartedMsg:
		if msg.err != nil {
			m.state = oauthStateList
			m.statusMsg = StyleError.Render("Error: " + msg.err.Error())
		} else {
			m.authorizeURL = msg.authorizeURL
			m.state = oauthStateBrowserWait
			m.statusMsg = StyleMuted.Render("Browser opened. Waiting…")
			openBrowser(msg.authorizeURL)
			cmds = append(cmds, m.spinner.Tick)
			if m.apiClient != nil {
				cmds = append(cmds, tea.Tick(2*time.Second, func(_ time.Time) tea.Msg {
					return doCheckOAuthStatus(m.apiClient, msg.provider)()
				}))
			}
		}

	case personalTokenSavedMsg:
		m.state = oauthStateList
		if msg.err != nil {
			m.statusMsg = StyleError.Render("Error saving token: " + msg.err.Error())
		} else {
			m.statusMsg = StyleOK.Render(providers[m.cursor].Name + " token saved!")
			m.statuses[providers[m.cursor].ID] = providerStatus{connected: true, checked: true}
		}

	case oauthRevokedMsg:
		if msg.err != nil {
			m.statusMsg = StyleError.Render("Error disconnecting: " + msg.err.Error())
		} else {
			m.statusMsg = StyleOK.Render(providers[m.cursor].Name + " disconnected")
			m.statuses[msg.provider] = providerStatus{connected: false, checked: true}
		}

	case tea.KeyMsg:
		switch m.state {
		case oauthStateList:
			cmds = append(cmds, m.handleListKey(msg)...)
		case oauthStateTokenInput:
			cmds = append(cmds, m.handleTokenInputKey(msg)...)
		case oauthStateSetupGuide:
			switch msg.String() {
			case "esc", "q":
				m.state = oauthStateList
			case "enter":
				if m.apiClient != nil {
					p := providers[m.cursor]
					m.statusMsg = StyleMuted.Render("Starting OAuth flow…")
					m.state = oauthStateList
					cmds = append(cmds, doStartOAuthFlow(m.apiClient, p.ID))
				}
			}
		case oauthStateShopInput:
			cmds = append(cmds, m.handleShopInputKey(msg)...)
		case oauthStateBrowserWait:
			if msg.String() == "esc" {
				m.state = oauthStateList
			}
		}
	}

	return m, tea.Batch(cmds...)
}

func (m *OAuthModel) handleListKey(msg tea.KeyMsg) []tea.Cmd {
	var cmds []tea.Cmd
	switch msg.String() {
	case "up", "k":
		if m.cursor > 0 {
			m.cursor--
		}
	case "down", "j":
		if m.cursor < len(providers)-1 {
			m.cursor++
		}
	case "enter", " ":
		cmds = append(cmds, m.activateProvider()...)
	case "d":
		cmds = append(cmds, m.disconnectProvider()...)
	case "r":
		if m.apiClient != nil {
			for _, p := range providers {
				cmds = append(cmds, doCheckOAuthStatus(m.apiClient, p.ID))
			}
		}
	}
	return cmds
}

func (m *OAuthModel) activateProvider() []tea.Cmd {
	p := providers[m.cursor]
	if m.statuses[p.ID].connected {
		return m.disconnectProvider()
	}
	switch p.AuthMethod {
	case "token", "token+extra":
		m.state = oauthStateTokenInput
		m.tokenErr = ""
		m.buildTokenInputs(p)
		return []tea.Cmd{textinput.Blink}
	case "browser":
		m.state = oauthStateSetupGuide
		return nil
	case "browser+shop":
		m.state = oauthStateShopInput
		m.shopInput.SetValue("")
		m.shopInput.Focus()
		return []tea.Cmd{textinput.Blink}
	}
	return nil
}

func (m *OAuthModel) disconnectProvider() []tea.Cmd {
	if m.apiClient == nil {
		m.statusMsg = StyleError.Render("Not logged in — connect first")
		return nil
	}
	return []tea.Cmd{doRevokeOAuth(m.apiClient, providers[m.cursor].ID)}
}

func (m *OAuthModel) buildTokenInputs(p OAuthProvider) {
	fields := []string{p.TokenLabel}
	if p.TokenLabel == "" {
		fields[0] = "Token"
	}
	fields = append(fields, p.ExtraFields...)
	inputs := make([]textinput.Model, len(fields))
	for i, label := range fields {
		t := textinput.New()
		t.Placeholder = label
		t.CharLimit = 300
		if i == 0 {
			t.EchoMode = textinput.EchoPassword
		}
		inputs[i] = t
	}
	inputs[0].Focus()
	m.tokenInputs = inputs
	m.tokenFocused = 0
}

func (m *OAuthModel) handleTokenInputKey(msg tea.KeyMsg) []tea.Cmd {
	var cmds []tea.Cmd
	switch msg.String() {
	case "esc":
		m.state = oauthStateList
	case "tab", "down":
		m.tokenInputs[m.tokenFocused].Blur()
		m.tokenFocused = (m.tokenFocused + 1) % len(m.tokenInputs)
		m.tokenInputs[m.tokenFocused].Focus()
		cmds = append(cmds, textinput.Blink)
	case "shift+tab", "up":
		m.tokenInputs[m.tokenFocused].Blur()
		m.tokenFocused = (m.tokenFocused - 1 + len(m.tokenInputs)) % len(m.tokenInputs)
		m.tokenInputs[m.tokenFocused].Focus()
		cmds = append(cmds, textinput.Blink)
	case "enter":
		if m.tokenFocused < len(m.tokenInputs)-1 {
			m.tokenInputs[m.tokenFocused].Blur()
			m.tokenFocused++
			m.tokenInputs[m.tokenFocused].Focus()
			cmds = append(cmds, textinput.Blink)
		} else {
			cmds = append(cmds, m.submitToken()...)
		}
	case "ctrl+s":
		cmds = append(cmds, m.submitToken()...)
	default:
		var c tea.Cmd
		m.tokenInputs[m.tokenFocused], c = m.tokenInputs[m.tokenFocused].Update(msg)
		cmds = append(cmds, c)
	}
	return cmds
}

func (m *OAuthModel) handleShopInputKey(msg tea.KeyMsg) []tea.Cmd {
	var cmds []tea.Cmd
	switch msg.String() {
	case "esc":
		m.state = oauthStateList
	case "enter":
		shop := strings.TrimSpace(m.shopInput.Value())
		if shop == "" {
			m.tokenErr = StyleError.Render("Store domain cannot be empty")
			return nil
		}
		if m.apiClient == nil {
			m.tokenErr = StyleError.Render("Not logged in — connect first")
			return nil
		}
		m.state = oauthStateBrowserWait
		cmds = append(cmds, doStartOAuthFlowWithShop(m.apiClient, "shopify", shop))
	default:
		var c tea.Cmd
		m.shopInput, c = m.shopInput.Update(msg)
		cmds = append(cmds, c)
	}
	return cmds
}

func (m *OAuthModel) submitToken() []tea.Cmd {
	if m.apiClient == nil {
		m.tokenErr = StyleError.Render("Not logged in — connect first")
		return nil
	}
	p := providers[m.cursor]
	token := strings.TrimSpace(m.tokenInputs[0].Value())
	if token == "" {
		m.tokenErr = StyleError.Render("Token cannot be empty")
		return nil
	}
	extra := map[string]string{}
	for i, field := range p.ExtraFields {
		if i+1 < len(m.tokenInputs) {
			extra[field] = strings.TrimSpace(m.tokenInputs[i+1].Value())
		}
	}
	return []tea.Cmd{doStorePersonalToken(m.apiClient, p.ID, token, extra)}
}

// ---------------------------------------------------------------------------
// View
// ---------------------------------------------------------------------------

func (m OAuthModel) View() string {
	var sb strings.Builder
	sb.WriteString(StyleHeader.Render("  OAuth Connections") + "\n\n")
	if m.apiClient == nil {
		sb.WriteString(StyleWarning.Render("  ⚠  Not connected — saving requires login (tab 1).") + "\n\n")
	}
	switch m.state {
	case oauthStateList:
		sb.WriteString(m.renderProviderList())
	case oauthStateTokenInput:
		sb.WriteString(m.renderTokenForm())
	case oauthStateSetupGuide:
		sb.WriteString(m.renderSetupGuide())
	case oauthStateBrowserWait:
		sb.WriteString(m.renderBrowserWait())
	case oauthStateShopInput:
		sb.WriteString(m.renderShopInput())
	}
	if m.statusMsg != "" {
		sb.WriteString("\n  " + m.statusMsg + "\n")
	}
	return sb.String()
}

func (m OAuthModel) renderProviderList() string {
	var sb strings.Builder

	sb.WriteString(StyleMuted.Render("  ── Token-based (paste your personal token) ──────────────────") + "\n\n")
	for i, p := range providers {
		if p.AuthMethod != "token" && p.AuthMethod != "token+extra" {
			continue
		}
		sb.WriteString(m.renderRow(i, p))
	}

	sb.WriteString("\n" + StyleMuted.Render("  ── Browser OAuth (register your own app with the provider) ─") + "\n\n")
	for i, p := range providers {
		if p.AuthMethod != "browser" && p.AuthMethod != "browser+shop" {
			continue
		}
		sb.WriteString(m.renderRow(i, p))
	}

	sb.WriteString("\n" + StyleHelp.Render("  ↑/↓ j/k: move  Enter: connect  d: disconnect  r: refresh"))
	return sb.String()
}

func (m OAuthModel) renderRow(i int, p OAuthProvider) string {
	st := m.statuses[p.ID]
	cur := "   "
	if i == m.cursor {
		cur = StyleWarning.Render(" ▶ ")
	}

	var status string
	if !st.checked {
		status = StyleMuted.Render("○ checking      ")
	} else if st.connected {
		status = StyleOK.Render("● connected     ")
	} else {
		status = StyleMuted.Render("○ not connected ")
	}

	var action string
	if st.connected {
		action = StyleError.Render("[d: Disconnect]")
	} else if m.apiClient == nil && (p.AuthMethod == "browser" || p.AuthMethod == "browser+shop") {
		action = StyleMuted.Render("[Log in first]")
	} else if p.AuthMethod == "browser" || p.AuthMethod == "browser+shop" {
		action = StyleWarning.Render("[Enter: Setup guide]")
	} else if p.AuthMethod == "token+extra" {
		action = StyleWarning.Render("[Enter: Token + fields]")
	} else {
		action = StyleWarning.Render("[Enter: Paste token]")
	}

	name := p.Name
	if i == m.cursor {
		name = StylePrimary().Render(fmt.Sprintf("%-15s", name))
	} else {
		name = fmt.Sprintf("%-15s", name)
	}
	return fmt.Sprintf("%s%s %s %s\n", cur, name, status, action)
}

func (m OAuthModel) resolvedHelp(raw string) string {
	apiURL := "http://localhost:8080"
	if m.apiClient != nil && m.apiClient.BaseURL != "" {
		apiURL = m.apiClient.BaseURL
	}
	return strings.ReplaceAll(raw, "{YOUR_API_URL}", apiURL)
}

func (m OAuthModel) renderTokenForm() string {
	p := providers[m.cursor]
	var sb strings.Builder
	sb.WriteString(StyleHeader.Render(fmt.Sprintf("  Connect %s", p.Name)) + "\n\n")
	sb.WriteString("  " + StyleMuted.Render(p.Description) + "\n\n")
	for _, line := range strings.Split(m.resolvedHelp(p.TokenHelp), "\n") {
		sb.WriteString("  " + StyleMuted.Render(line) + "\n")
	}
	sb.WriteString("\n")

	labels := []string{p.TokenLabel}
	if p.TokenLabel == "" {
		labels[0] = "Token"
	}
	labels = append(labels, p.ExtraFields...)
	for i, label := range labels {
		style := StyleMuted
		if i == m.tokenFocused {
			style = StyleWarning
		}
		sb.WriteString("  " + style.Render(label+":") + "\n")
		if i < len(m.tokenInputs) {
			sb.WriteString("  " + m.tokenInputs[i].View() + "\n\n")
		}
	}
	if m.tokenErr != "" {
		sb.WriteString("  " + m.tokenErr + "\n")
	}
	sb.WriteString("\n" + StyleHelp.Render("  Tab/↑↓: move  Enter: next / Ctrl+S: save  Esc: cancel"))
	return sb.String()
}

func (m OAuthModel) renderSetupGuide() string {
	p := providers[m.cursor]
	var sb strings.Builder
	sb.WriteString(StyleHeader.Render(fmt.Sprintf("  Setup Guide — %s", p.Name)) + "\n\n")
	sb.WriteString("  " + StyleMuted.Render(p.Description) + "\n\n")
	if p.EnvVars != "" {
		sb.WriteString("  " + StyleWarning.Render("Env vars needed: "+p.EnvVars) + "\n\n")
	}
	for _, line := range strings.Split(m.resolvedHelp(p.TokenHelp), "\n") {
		sb.WriteString("  " + StyleMuted.Render(line) + "\n")
	}
	sb.WriteString("\n")
	if m.apiClient != nil {
		sb.WriteString("  " + StyleOK.Render("Env vars set and server restarted?") + "\n")
		sb.WriteString("  " + StyleWarning.Render("Press Enter to open browser and authorize.") + "\n")
	} else {
		sb.WriteString("  " + StyleMuted.Render("Log in first (tab 1), set env vars, restart server.") + "\n")
	}
	sb.WriteString("\n" + StyleHelp.Render("  Enter: open browser  Esc/q: back"))
	return sb.String()
}

func (m OAuthModel) renderShopInput() string {
	var sb strings.Builder
	sb.WriteString(StyleHeader.Render("  Connect Shopify") + "\n\n")
	for _, line := range strings.Split(providers[m.cursor].TokenHelp, "\n") {
		sb.WriteString("  " + StyleMuted.Render(line) + "\n")
	}
	sb.WriteString("\n  " + StyleWarning.Render("Your store domain:") + "\n")
	sb.WriteString("  " + m.shopInput.View() + "\n")
	sb.WriteString("  " + StyleMuted.Render("e.g. my-store.myshopify.com or just: my-store") + "\n")
	if m.tokenErr != "" {
		sb.WriteString("\n  " + m.tokenErr + "\n")
	}
	sb.WriteString("\n" + StyleHelp.Render("  Enter: continue  Esc: cancel"))
	return sb.String()
}

func (m OAuthModel) renderBrowserWait() string {
	p := providers[m.cursor]
	var sb strings.Builder
	sb.WriteString(StyleHeader.Render(fmt.Sprintf("  Connecting %s", p.Name)) + "\n\n")
	if m.authorizeURL != "" {
		sb.WriteString("  URL: " + StyleCyan().Render(m.authorizeURL) + "\n\n")
	}
	sb.WriteString("  " + m.spinner.View() + " Waiting for authorization in browser…\n")
	sb.WriteString("  " + StyleMuted.Render("If browser didn't open, copy the URL above.") + "\n")
	sb.WriteString("\n" + StyleHelp.Render("  Esc: cancel"))
	return sb.String()
}

// ---------------------------------------------------------------------------
// Style helpers
// ---------------------------------------------------------------------------

type styleRenderer func(string) string

func (f styleRenderer) Render(s string) string { return f(s) }

var (
	stylePrimaryInner = StyleTabActive
	styleCyanInner    = lipgloss.NewStyle().Foreground(lipgloss.Color(colorCyan))
)

func StylePrimary() styleRenderer {
	return func(s string) string { return stylePrimaryInner.Render(s) }
}

func StyleCyan() styleRenderer {
	return func(s string) string { return styleCyanInner.Render(s) }
}

// ---------------------------------------------------------------------------
// Async commands
// ---------------------------------------------------------------------------

func doCheckOAuthStatus(client *api.Client, provider string) tea.Cmd {
	return func() tea.Msg {
		resp, err := client.OAuthStatus(context.Background(), provider)
		if err != nil {
			return oauthStatusMsg{provider: provider, err: err}
		}
		return oauthStatusMsg{provider: provider, connected: resp.Connected}
	}
}

func doStartOAuthFlow(client *api.Client, provider string) tea.Cmd {
	return func() tea.Msg {
		url, err := client.StartOAuthFlow(context.Background(), provider)
		if err != nil {
			return oauthFlowStartedMsg{provider: provider, err: err}
		}
		return oauthFlowStartedMsg{provider: provider, authorizeURL: url}
	}
}

func doStartOAuthFlowWithShop(client *api.Client, provider, shop string) tea.Cmd {
	return func() tea.Msg {
		url, err := client.StartOAuthFlowWithShop(context.Background(), provider, shop)
		if err != nil {
			return oauthFlowStartedMsg{provider: provider, err: err}
		}
		return oauthFlowStartedMsg{provider: provider, authorizeURL: url}
	}
}

func doStorePersonalToken(client *api.Client, provider, token string, extra map[string]string) tea.Cmd {
	return func() tea.Msg {
		err := client.StorePersonalToken(context.Background(), provider, token, extra)
		return personalTokenSavedMsg{provider: provider, err: err}
	}
}

func doRevokeOAuth(client *api.Client, provider string) tea.Cmd {
	return func() tea.Msg {
		err := client.RevokeOAuth(context.Background(), provider)
		return oauthRevokedMsg{provider: provider, err: err}
	}
}

func openBrowser(url string) {
	var cmd *exec.Cmd
	switch runtime.GOOS {
	case "darwin":
		cmd = exec.Command("open", url)
	case "windows":
		cmd = exec.Command("cmd", "/c", "start", url)
	default:
		cmd = exec.Command("xdg-open", url)
	}
	_ = cmd.Start()
}
