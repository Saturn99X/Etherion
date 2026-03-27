package ui

import (
	"context"
	"fmt"
	"strings"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/etherion-ai/etherion/tui/internal/api"
)

// KBModel shows which vendor integrations are connected and feeding the knowledge base.
type KBModel struct {
	sources   []api.KBSource
	cursor    int
	err       string
	apiClient *api.Client
}

func NewKBModel(apiClient *api.Client) KBModel {
	return KBModel{apiClient: apiClient}
}

func (m KBModel) Init() tea.Cmd { return nil }

func (m KBModel) Update(msg tea.Msg) (KBModel, tea.Cmd) {
	var cmds []tea.Cmd

	switch msg := msg.(type) {
	case tea.KeyMsg:
		switch msg.String() {
		case "up", "k":
			if m.cursor > 0 {
				m.cursor--
			}
		case "down", "j":
			if m.cursor < len(m.sources)-1 {
				m.cursor++
			}
		case "r":
			cmds = append(cmds, m.loadSources())
		}

	case graphqlResultMsg:
		if msg.tab != tabKB {
			break
		}
		if msg.err != nil {
			m.err = msg.err.Error()
			break
		}
		m.err = ""
		if raw, ok := msg.data["getIntegrations"]; ok {
			m.sources = decodeKBSources(raw)
		}
	}

	return m, tea.Batch(cmds...)
}

func (m *KBModel) loadSources() tea.Cmd {
	if m.apiClient == nil {
		return nil
	}
	client := m.apiClient
	return func() tea.Msg {
		// tenant_id is ignored by the server — auth context determines tenant.
		q := `query { getIntegrations(tenant_id: 0) { serviceName status lastConnected capabilities } }`
		resp, err := client.GraphQL(context.Background(), q, nil)
		return graphqlResultMsg{data: resp.Data, tab: tabKB, err: err}
	}
}

func (m KBModel) View() string {
	var sb strings.Builder
	sb.WriteString(StyleHeader.Render("  Knowledge Base — Sources") + "\n\n")

	if m.apiClient == nil {
		sb.WriteString(StyleWarning.Render("  Connect to server first (tab 1)\n"))
		return sb.String()
	}

	if m.err != "" {
		sb.WriteString(StyleError.Render("  Error: "+m.err) + "\n\n")
	}

	if len(m.sources) == 0 {
		sb.WriteString(StyleMuted.Render("  No integrations configured. Press r to refresh.\n"))
		sb.WriteString("\n")
		sb.WriteString(StyleMuted.Render("  Connect vendors via the OAuth tab (5) to populate the KB.\n"))
	} else {
		connected := 0
		for _, s := range m.sources {
			if s.Status == "connected" {
				connected++
			}
		}
		sb.WriteString(StyleMuted.Render(fmt.Sprintf("  %d/%d providers connected\n\n", connected, len(m.sources))))

		sb.WriteString(StyleMuted.Render(fmt.Sprintf("  %-18s %-12s  %s", "Provider", "Status", "Capabilities")) + "\n")
		sb.WriteString(StyleMuted.Render("  "+strings.Repeat("─", 60)) + "\n")

		for i, src := range m.sources {
			cursor := "   "
			if i == m.cursor {
				cursor = StyleWarning.Render(" ▶ ")
			}

			name := src.ServiceName
			if len(name) > 16 {
				name = name[:13] + "…"
			}

			var statusStr string
			if src.Status == "connected" {
				statusStr = StyleOK.Render("● connected ")
			} else {
				statusStr = StyleMuted.Render("○ " + src.Status + "    ")
			}

			caps := strings.Join(src.Capabilities, ", ")
			if len(caps) > 30 {
				caps = caps[:27] + "…"
			}
			if caps == "" {
				caps = StyleMuted.Render("—")
			}

			row := fmt.Sprintf("%s%-18s %s  %s", cursor, name, statusStr, caps)
			if i == m.cursor {
				sb.WriteString(StyleWarning.Render(row) + "\n")
			} else {
				sb.WriteString(row + "\n")
			}
		}

		sb.WriteString("\n")
		sb.WriteString(StyleMuted.Render("  Connected providers sync their data into the vector KB\n"))
		sb.WriteString(StyleMuted.Render("  automatically after each OAuth flow or token connection.\n"))
	}

	sb.WriteString("\n" + StyleHelp.Render("  ↑↓/j/k: move  r: refresh  OAuth tab (5): connect providers"))
	return sb.String()
}

// ---------------------------------------------------------------------------
// Decode helper
// ---------------------------------------------------------------------------

func decodeKBSources(raw interface{}) []api.KBSource {
	slice, ok := raw.([]interface{})
	if !ok {
		return nil
	}
	out := make([]api.KBSource, 0, len(slice))
	for _, item := range slice {
		m, ok := item.(map[string]interface{})
		if !ok {
			continue
		}
		s := api.KBSource{}
		if v, ok := m["serviceName"].(string); ok {
			s.ServiceName = v
		}
		if v, ok := m["status"].(string); ok {
			s.Status = v
		}
		if v, ok := m["lastConnected"].(string); ok {
			s.LastConnected = v
		}
		if raw, ok := m["capabilities"]; ok {
			if caps, ok := raw.([]interface{}); ok {
				for _, cap := range caps {
					if c, ok := cap.(string); ok {
						s.Capabilities = append(s.Capabilities, c)
					}
				}
			}
		}
		out = append(out, s)
	}
	return out
}
