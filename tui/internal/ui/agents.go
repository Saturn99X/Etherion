package ui

import (
	"context"
	"fmt"
	"strings"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/etherion-ai/etherion/tui/internal/api"
)

// AgentsModel shows agent teams and individual agents fetched via GraphQL.
type AgentsModel struct {
	teams      []api.AgentTeam
	teamCursor int
	err        string
	apiClient  *api.Client
}

func NewAgentsModel() AgentsModel {
	return AgentsModel{}
}

func (m AgentsModel) Init() tea.Cmd { return nil }

func (m AgentsModel) Update(msg tea.Msg) (AgentsModel, tea.Cmd) {
	var cmds []tea.Cmd

	switch msg := msg.(type) {
	case tea.KeyMsg:
		switch msg.String() {
		case "up", "k":
			if m.teamCursor > 0 {
				m.teamCursor--
			}
		case "down", "j":
			if m.teamCursor < len(m.teams)-1 {
				m.teamCursor++
			}
		case "r":
			cmds = append(cmds, m.loadTeams())
		}

	case graphqlResultMsg:
		if msg.tab != tabAgents {
			break
		}
		if msg.err != nil {
			m.err = msg.err.Error()
			break
		}
		m.err = ""
		if teams, ok := msg.data["agentTeams"]; ok {
			m.teams = decodeAgentTeams(teams)
		}
	}

	return m, tea.Batch(cmds...)
}

func (m *AgentsModel) loadTeams() tea.Cmd {
	if m.apiClient == nil {
		return nil
	}
	client := m.apiClient
	return func() tea.Msg {
		q := `query ListAgentTeams { agentTeams { id name description agents { id name role description } } }`
		resp, err := client.GraphQL(context.Background(), q, nil)
		return graphqlResultMsg{data: resp.Data, tab: tabAgents, err: err}
	}
}

func (m AgentsModel) View() string {
	var sb strings.Builder
	sb.WriteString(StyleHeader.Render("  Agent Teams") + "\n\n")

	if m.apiClient == nil {
		sb.WriteString(StyleWarning.Render("  Connect to server first (tab 1)\n"))
		return sb.String()
	}

	if m.err != "" {
		sb.WriteString(StyleError.Render("  Error: "+m.err) + "\n\n")
	}

	if len(m.teams) == 0 {
		sb.WriteString(StyleMuted.Render("  No agent teams found. Press r to refresh.\n"))
	} else {
		sb.WriteString(StyleMuted.Render(fmt.Sprintf("  %-24s %-6s  %s", "Team", "Agents", "Description")) + "\n")
		sb.WriteString(StyleMuted.Render("  "+strings.Repeat("─", 60)) + "\n")

		for i, team := range m.teams {
			cursor := "   "
			if i == m.teamCursor {
				cursor = StyleWarning.Render(" ▶ ")
			}

			name := team.Name
			if len(name) > 22 {
				name = name[:19] + "…"
			}
			desc := team.Description
			if len(desc) > 30 {
				desc = desc[:27] + "…"
			}

			if i == m.teamCursor {
				name = StylePrimary().Render(name)
			}

			sb.WriteString(fmt.Sprintf("%s%-22s %-6d  %s\n",
				cursor, name, len(team.Agents), desc))
		}

		// Show agents for the selected team.
		if m.teamCursor < len(m.teams) {
			team := m.teams[m.teamCursor]
			if len(team.Agents) > 0 {
				sb.WriteString("\n  " + StyleMuted.Render("Agents in "+team.Name+":") + "\n")
				for _, a := range team.Agents {
					sb.WriteString(fmt.Sprintf("    • %-20s %s\n", a.Name, StyleMuted.Render(a.Role)))
				}
			}
		}
	}

	sb.WriteString("\n" + StyleHelp.Render("  ↑↓/j/k: select team  r: refresh"))
	return sb.String()
}

// ---------------------------------------------------------------------------
// Decode helpers
// ---------------------------------------------------------------------------

func decodeAgentTeams(raw interface{}) []api.AgentTeam {
	slice, ok := raw.([]interface{})
	if !ok {
		return nil
	}
	out := make([]api.AgentTeam, 0, len(slice))
	for _, item := range slice {
		m, ok := item.(map[string]interface{})
		if !ok {
			continue
		}
		t := api.AgentTeam{}
		if v, ok := m["id"].(string); ok {
			t.ID = v
		}
		if v, ok := m["name"].(string); ok {
			t.Name = v
		}
		if v, ok := m["description"].(string); ok {
			t.Description = v
		}
		if raw, ok := m["agents"]; ok {
			t.Agents = decodeAgents(raw)
		}
		out = append(out, t)
	}
	return out
}

func decodeAgents(raw interface{}) []api.Agent {
	slice, ok := raw.([]interface{})
	if !ok {
		return nil
	}
	out := make([]api.Agent, 0, len(slice))
	for _, item := range slice {
		m, ok := item.(map[string]interface{})
		if !ok {
			continue
		}
		a := api.Agent{}
		if v, ok := m["id"].(string); ok {
			a.ID = v
		}
		if v, ok := m["name"].(string); ok {
			a.Name = v
		}
		if v, ok := m["role"].(string); ok {
			a.Role = v
		}
		if v, ok := m["description"].(string); ok {
			a.Description = v
		}
		out = append(out, a)
	}
	return out
}
