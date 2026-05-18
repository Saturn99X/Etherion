package ui

import (
	"context"
	"fmt"
	"strings"

	"github.com/charmbracelet/bubbles/textinput"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/etherion-ai/etherion/tui/internal/api"
)

type agentViewMode int

const (
	agentModeList      agentViewMode = iota
	agentModeCreate                   // 3-field create form
	agentModeTools                    // tool scoping panel
	agentModeDetail                   // view team details + actions
	agentModeEdit                     // edit team name/description
	agentModeDelete                   // delete confirmation
	agentModeProposals                // list pending proposals from IO
	agentModeProposalDetail           // view proposal + approve/reject
)

const (
	agentFieldName = iota
	agentFieldDesc
	agentFieldSpec
	agentFieldCount
)

const (
	agentEditFieldName = iota
	agentEditFieldDesc
	agentEditFieldCount
)

// AgentsModel lists agent teams, provides a create-new-team form, tool scoping,
// team detail view, edit, delete, and proposal approval.
type AgentsModel struct {
	mode       agentViewMode
	teams      []api.AgentTeam
	teamCursor int

	// Create form fields.
	inputs  [agentFieldCount]textinput.Model
	focused int

	// Edit form fields (for detail view).
	editInputs  [agentEditFieldCount]textinput.Model
	editFocused int

	// Tool scoping state.
	availableTools []api.MCPTool
	selectedTools  map[string]bool
	toolCursor     int
	scopingTeamID  string
	toolsLoading   bool

	// Proposals (ValidationGate).
	proposals      []api.Proposal
	proposalCursor int

	// Detail view: which team is being inspected.
	detailTeamID string

	status  string
	loading bool
	err     string

	apiClient *api.Client
}

func NewAgentsModel(apiClient *api.Client) AgentsModel {
	nameInput := textinput.New()
	nameInput.Placeholder = "e.g. Research Team"
	nameInput.CharLimit = 60
	nameInput.Width = 50

	descInput := textinput.New()
	descInput.Placeholder = "Short description of this team's purpose"
	descInput.CharLimit = 160
	descInput.Width = 50

	specInput := textinput.New()
	specInput.Placeholder = "Natural language — what should this team do and achieve?"
	specInput.CharLimit = 400
	specInput.Width = 60

	eName := textinput.New()
	eName.Placeholder = "Team name"
	eName.CharLimit = 60
	eName.Width = 50

	eDesc := textinput.New()
	eDesc.Placeholder = "Team description"
	eDesc.CharLimit = 160
	eDesc.Width = 50

	return AgentsModel{
		mode:          agentModeList,
		apiClient:     apiClient,
		inputs:        [agentFieldCount]textinput.Model{nameInput, descInput, specInput},
		editInputs:    [agentEditFieldCount]textinput.Model{eName, eDesc},
		selectedTools: make(map[string]bool),
	}
}

func (m AgentsModel) Init() tea.Cmd { return nil }

func (m AgentsModel) Update(msg tea.Msg) (AgentsModel, tea.Cmd) {
	var cmds []tea.Cmd

	switch msg := msg.(type) {
	case tea.KeyMsg:
		switch m.mode {

		// ── tool scoping ──────────────────────────────────────────────────
		case agentModeTools:
			switch msg.String() {
			case "esc":
				m.mode = agentModeDetail
				m.status = ""
				return m, nil
			case "up", "k":
				if m.toolCursor > 0 {
					m.toolCursor--
				}
			case "down", "j":
				if m.toolCursor < len(m.availableTools)-1 {
					m.toolCursor++
				}
			case " ":
				if m.toolCursor < len(m.availableTools) {
					name := m.availableTools[m.toolCursor].Name
					m.selectedTools[name] = !m.selectedTools[name]
				}
			case "a":
				for _, t := range m.availableTools {
					m.selectedTools[t.Name] = true
				}
			case "A":
				m.selectedTools = make(map[string]bool)
			case "enter", "ctrl+s":
				if m.scopingTeamID == "" {
					return m, nil
				}
				selected := m.collectSelected()
				m.loading = true
				m.status = "Saving tool scope…"
				cmds = append(cmds, m.saveToolScope(m.scopingTeamID, selected))
			}

		// ── create form ───────────────────────────────────────────────────
		case agentModeCreate:
			switch msg.String() {
			case "esc":
				m.mode = agentModeList
				m.status = ""
				m.loading = false
				m.clearForm()
				return m, nil
			case "tab":
				m.inputs[m.focused].Blur()
				m.focused = (m.focused + 1) % agentFieldCount
				m.inputs[m.focused].Focus()
				return m, nil
			case "shift+tab":
				m.inputs[m.focused].Blur()
				m.focused = (m.focused - 1 + agentFieldCount) % agentFieldCount
				m.inputs[m.focused].Focus()
				return m, nil
			case "down":
				m.inputs[m.focused].Blur()
				m.focused = (m.focused + 1) % agentFieldCount
				m.inputs[m.focused].Focus()
				return m, nil
			case "up":
				m.inputs[m.focused].Blur()
				m.focused = (m.focused - 1 + agentFieldCount) % agentFieldCount
				m.inputs[m.focused].Focus()
				return m, nil
			case "enter", "ctrl+s":
				if m.focused < agentFieldCount-1 {
					m.inputs[m.focused].Blur()
					m.focused++
					m.inputs[m.focused].Focus()
					return m, nil
				}
				name := strings.TrimSpace(m.inputs[agentFieldName].Value())
				desc := strings.TrimSpace(m.inputs[agentFieldDesc].Value())
				spec := strings.TrimSpace(m.inputs[agentFieldSpec].Value())
				if name == "" || spec == "" {
					m.status = "Name and specification are required."
					return m, nil
				}
				if desc == "" {
					desc = spec
				}
				m.loading = true
				m.status = "Creating team…"
				cmds = append(cmds, m.createTeam(name, desc, spec))
				return m, tea.Batch(cmds...)
			default:
				var c tea.Cmd
				m.inputs[m.focused], c = m.inputs[m.focused].Update(msg)
				cmds = append(cmds, c)
				return m, tea.Batch(cmds...)
			}

		// ── edit form ─────────────────────────────────────────────────────
		case agentModeEdit:
			switch msg.String() {
			case "esc":
				m.mode = agentModeDetail
				m.status = ""
				return m, nil
			case "tab":
				m.editInputs[m.editFocused].Blur()
				m.editFocused = (m.editFocused + 1) % agentEditFieldCount
				m.editInputs[m.editFocused].Focus()
				return m, nil
			case "shift+tab":
				m.editInputs[m.editFocused].Blur()
				m.editFocused = (m.editFocused - 1 + agentEditFieldCount) % agentEditFieldCount
				m.editInputs[m.editFocused].Focus()
				return m, nil
			case "down":
				m.editInputs[m.editFocused].Blur()
				m.editFocused = (m.editFocused + 1) % agentEditFieldCount
				m.editInputs[m.editFocused].Focus()
				return m, nil
			case "up":
				m.editInputs[m.editFocused].Blur()
				m.editFocused = (m.editFocused - 1 + agentEditFieldCount) % agentEditFieldCount
				m.editInputs[m.editFocused].Focus()
				return m, nil
			case "enter", "ctrl+s":
				m.loading = true
				m.status = "Saving…"
				name := strings.TrimSpace(m.editInputs[agentEditFieldName].Value())
				desc := strings.TrimSpace(m.editInputs[agentEditFieldDesc].Value())
				cmds = append(cmds, m.updateTeam(m.detailTeamID, name, desc))
				return m, tea.Batch(cmds...)
			default:
				var c tea.Cmd
				m.editInputs[m.editFocused], c = m.editInputs[m.editFocused].Update(msg)
				cmds = append(cmds, c)
				return m, tea.Batch(cmds...)
			}

		// ── delete confirmation ───────────────────────────────────────────
		case agentModeDelete:
			switch msg.String() {
			case "y", "Y":
				m.loading = true
				m.status = "Deleting team…"
				cmds = append(cmds, m.deleteTeam(m.detailTeamID))
			case "n", "N", "esc":
				m.mode = agentModeDetail
				m.status = ""
			}

		// ── proposal detail ───────────────────────────────────────────────
		case agentModeProposalDetail:
			switch msg.String() {
			case "y", "Y":
				if m.proposalCursor < len(m.proposals) {
					pid := m.proposals[m.proposalCursor].ProposalID
					m.loading = true
					m.status = "Approving proposal…"
					cmds = append(cmds, m.approveProposal(pid))
				}
			case "n", "N":
				if m.proposalCursor < len(m.proposals) {
					pid := m.proposals[m.proposalCursor].ProposalID
					m.loading = true
					m.status = "Rejecting proposal…"
					cmds = append(cmds, m.rejectProposal(pid))
				}
			case "esc":
				m.mode = agentModeProposals
				m.status = ""
			}

		// ── proposals list ────────────────────────────────────────────────
		case agentModeProposals:
			switch msg.String() {
			case "up", "k":
				if m.proposalCursor > 0 {
					m.proposalCursor--
				}
			case "down", "j":
				if m.proposalCursor < len(m.proposals)-1 {
					m.proposalCursor++
				}
			case "enter":
				if len(m.proposals) > 0 {
					m.mode = agentModeProposalDetail
				}
			case "r":
				cmds = append(cmds, m.loadProposals())
			case "esc":
				m.mode = agentModeList
			}

		// ── detail view ──────────────────────────────────────────────────
		case agentModeDetail:
			switch msg.String() {
			case "esc":
				m.mode = agentModeList
				m.status = ""
				return m, nil
			case "e":
				// Load current values into edit form.
				for _, t := range m.teams {
					if t.ID == m.detailTeamID {
						m.editInputs[agentEditFieldName].SetValue(t.Name)
						m.editInputs[agentEditFieldDesc].SetValue(t.Description)
						break
					}
				}
				m.editFocused = 0
				m.mode = agentModeEdit
				m.status = ""
				m.editInputs[0].Focus()
				return m, textinput.Blink
			case "d":
				m.mode = agentModeDelete
				m.status = ""
			case "t", "s":
				// Open tool scoping for this team.
				for _, t := range m.teams {
					if t.ID == m.detailTeamID {
						if t.IsSystem {
							m.status = "System teams are immutable."
							return m, nil
						}
						m.scopingTeamID = t.ID
						m.selectedTools = make(map[string]bool)
						for _, tn := range t.PreApprovedToolNames {
							m.selectedTools[tn] = true
						}
						m.toolCursor = 0
						m.mode = agentModeTools
						m.status = ""
						if len(m.availableTools) == 0 {
							m.toolsLoading = true
							cmds = append(cmds, m.loadAvailableTools())
						}
						return m, tea.Batch(cmds...)
					}
				}
			}

		// ── list mode ─────────────────────────────────────────────────────
		default:
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
			case "n", "c":
				m.mode = agentModeCreate
				m.focused = 0
				m.status = ""
				m.err = ""
				m.clearForm()
				m.inputs[0].Focus()
				return m, textinput.Blink
			case "enter":
				// Open detail view for selected team.
				if len(m.teams) > 0 {
					m.detailTeamID = m.teams[m.teamCursor].ID
					m.mode = agentModeDetail
					m.status = ""
				}
			case "p":
				// Show pending proposals.
				m.mode = agentModeProposals
				m.status = ""
				cmds = append(cmds, m.loadProposals())
			case "t", "s":
				if len(m.teams) == 0 {
					return m, nil
				}
				team := m.teams[m.teamCursor]
				if team.IsSystem {
					m.status = "System teams are immutable."
					return m, nil
				}
				m.scopingTeamID = team.ID
				m.selectedTools = make(map[string]bool)
				for _, tn := range team.PreApprovedToolNames {
					m.selectedTools[tn] = true
				}
				m.toolCursor = 0
				m.mode = agentModeTools
				m.status = ""
				m.err = ""
				if len(m.availableTools) == 0 {
					m.toolsLoading = true
					cmds = append(cmds, m.loadAvailableTools())
				}
				return m, tea.Batch(cmds...)
			}
		}

	case graphqlResultMsg:
		if msg.tab != tabAgents {
			break
		}
		m.loading = false
		m.toolsLoading = false
		if msg.err != nil {
			m.err = msg.err.Error()
			m.status = ""
			break
		}
		m.err = ""

		// createAgentTeam → switch to tool scoping for the new team.
		if raw, ok := msg.data["createAgentTeam"]; ok {
			if teamMap, ok := raw.(map[string]interface{}); ok {
				newID, _ := teamMap["id"].(string)
				m.selectedTools = make(map[string]bool)
				if toolsRaw, ok := teamMap["preApprovedToolNames"]; ok {
					if toolSlice, ok := toolsRaw.([]interface{}); ok {
						for _, t := range toolSlice {
							if s, ok := t.(string); ok {
								m.selectedTools[s] = true
							}
						}
					}
				}
				m.detailTeamID = newID
				m.scopingTeamID = newID
				m.toolCursor = 0
				m.mode = agentModeDetail
				m.status = "Team created! Press t to adjust tools."
				m.clearForm()
				if len(m.availableTools) == 0 {
					m.toolsLoading = true
					cmds = append(cmds, m.loadAvailableTools())
				}
				cmds = append(cmds, m.loadTeams())
			}
			break
		}

		// updateAgentTeam (bool) → reload.
		if v, ok := msg.data["updateAgentTeam"].(bool); ok && v {
			m.mode = agentModeDetail
			m.status = "Team updated."
			cmds = append(cmds, m.loadTeams())
			break
		}

		// deleteAgentTeam (bool) → reload.
		if v, ok := msg.data["deleteAgentTeam"].(bool); ok && v {
			m.mode = agentModeList
			m.status = "Team deleted."
			cmds = append(cmds, m.loadTeams())
			break
		}

		// approveProposal / rejectProposal (bool) → reload proposals.
		if _, ok := msg.data["approveProposal"]; ok {
			m.status = "Proposal approved."
			cmds = append(cmds, m.loadProposals())
			cmds = append(cmds, m.loadTeams())
			break
		}
		if _, ok := msg.data["rejectProposal"]; ok {
			m.status = "Proposal rejected."
			cmds = append(cmds, m.loadProposals())
			break
		}

		// listProposals → update proposals.
		if raw, ok := msg.data["listProposals"]; ok {
			m.proposals = decodeProposals(raw)
			if m.status == "Refreshing…" {
				m.status = ""
			}
		}

		// listAgentTeams → update teams.
		if teams, ok := msg.data["listAgentTeams"]; ok {
			m.teams = decodeAgentTeams(teams)
			if m.status == "Refreshing…" {
				m.status = ""
			}
		}

		// getAvailableMCPTools → update tool list.
		if raw, ok := msg.data["getAvailableMCPTools"]; ok {
			m.availableTools = decodeMCPTools(raw)
		}
	}

	return m, tea.Batch(cmds...)
}

// ── GraphQL commands ──────────────────────────────────────────────────────────

func (m *AgentsModel) loadTeams() tea.Cmd {
	if m.apiClient == nil {
		return nil
	}
	client := m.apiClient
	return func() tea.Msg {
		q := `query { listAgentTeams { id name description isActive isSystemTeam customAgentIDs preApprovedToolNames } }`
		resp, err := client.GraphQL(context.Background(), q, nil)
		return graphqlResultMsg{data: resp.Data, tab: tabAgents, err: err}
	}
}

func (m *AgentsModel) loadAvailableTools() tea.Cmd {
	if m.apiClient == nil {
		return nil
	}
	client := m.apiClient
	return func() tea.Msg {
		q := `query { getAvailableMCPTools { name description category status } }`
		resp, err := client.GraphQL(context.Background(), q, nil)
		return graphqlResultMsg{data: resp.Data, tab: tabAgents, err: err}
	}
}

func (m *AgentsModel) createTeam(name, desc, spec string) tea.Cmd {
	client := m.apiClient
	return func() tea.Msg {
		q := `mutation CreateTeam($name: String!, $description: String!, $specification: String!) {
			createAgentTeam(team_input: {name: $name, description: $description, specification: $specification}) {
				id name description isActive preApprovedToolNames
			}
		}`
		vars := map[string]interface{}{
			"name": name, "description": desc, "specification": spec,
		}
		resp, err := client.GraphQL(context.Background(), q, vars)
		return graphqlResultMsg{data: resp.Data, tab: tabAgents, err: err}
	}
}

func (m *AgentsModel) updateTeam(teamID, name, desc string) tea.Cmd {
	client := m.apiClient
	return func() tea.Msg {
		q := `mutation UpdateTeam($id: String!, $name: String!, $desc: String!) {
			updateAgentTeam(agent_team_id: $id, name: $name, description: $desc)
		}`
		vars := map[string]interface{}{"id": teamID, "name": name, "desc": desc}
		resp, err := client.GraphQL(context.Background(), q, vars)
		return graphqlResultMsg{data: resp.Data, tab: tabAgents, err: err}
	}
}

func (m *AgentsModel) deleteTeam(teamID string) tea.Cmd {
	client := m.apiClient
	return func() tea.Msg {
		q := `mutation DeleteTeam($id: String!) {
			deleteAgentTeam(agent_team_id: $id)
		}`
		vars := map[string]interface{}{"id": teamID}
		resp, err := client.GraphQL(context.Background(), q, vars)
		return graphqlResultMsg{data: resp.Data, tab: tabAgents, err: err}
	}
}

func (m *AgentsModel) saveToolScope(teamID string, tools []string) tea.Cmd {
	client := m.apiClient
	toolsIface := make([]interface{}, len(tools))
	for i, t := range tools {
		toolsIface[i] = t
	}
	return func() tea.Msg {
		q := `mutation ScopeTools($teamId: String!, $tools: [String!]!) {
			updateAgentTeam(agent_team_id: $teamId, pre_approved_tool_names: $tools)
		}`
		vars := map[string]interface{}{"teamId": teamID, "tools": toolsIface}
		resp, err := client.GraphQL(context.Background(), q, vars)
		return graphqlResultMsg{data: resp.Data, tab: tabAgents, err: err}
	}
}

func (m *AgentsModel) loadProposals() tea.Cmd {
	if m.apiClient == nil {
		return nil
	}
	client := m.apiClient
	return func() tea.Msg {
		q := `query { listProposals { proposalId actionType params proposer createdAt } }`
		resp, err := client.GraphQL(context.Background(), q, nil)
		return graphqlResultMsg{data: resp.Data, tab: tabAgents, err: err}
	}
}

func (m *AgentsModel) approveProposal(proposalID string) tea.Cmd {
	client := m.apiClient
	return func() tea.Msg {
		q := `mutation Approve($id: String!) { approveProposal(proposalId: $id) }`
		vars := map[string]interface{}{"id": proposalID}
		resp, err := client.GraphQL(context.Background(), q, vars)
		return graphqlResultMsg{data: resp.Data, tab: tabAgents, err: err}
	}
}

func (m *AgentsModel) rejectProposal(proposalID string) tea.Cmd {
	client := m.apiClient
	return func() tea.Msg {
		q := `mutation Reject($id: String!) { rejectProposal(proposalId: $id) }`
		vars := map[string]interface{}{"id": proposalID}
		resp, err := client.GraphQL(context.Background(), q, vars)
		return graphqlResultMsg{data: resp.Data, tab: tabAgents, err: err}
	}
}

func (m *AgentsModel) collectSelected() []string {
	out := make([]string, 0, len(m.selectedTools))
	for name, on := range m.selectedTools {
		if on {
			out = append(out, name)
		}
	}
	return out
}

func (m *AgentsModel) clearForm() {
	for i := range m.inputs {
		m.inputs[i].SetValue("")
		m.inputs[i].Blur()
	}
}

// ── Views ─────────────────────────────────────────────────────────────────────

func (m AgentsModel) View() string {
	if m.apiClient == nil {
		var sb strings.Builder
		sb.WriteString(StyleHeader.Render("  Agent Teams") + "\n\n")
		sb.WriteString(StyleWarning.Render("  Connect to server first (tab 1)\n"))
		return sb.String()
	}
	switch m.mode {
	case agentModeCreate:
		return m.viewCreateForm()
	case agentModeTools:
		return m.viewToolScope()
	case agentModeDetail:
		return m.viewDetail()
	case agentModeEdit:
		return m.viewEditForm()
	case agentModeDelete:
		return m.viewDeleteConfirm()
	case agentModeProposals:
		return m.viewProposals()
	case agentModeProposalDetail:
		return m.viewProposalDetail()
	default:
		return m.viewList()
	}
}

func (m AgentsModel) viewList() string {
	var sb strings.Builder
	sb.WriteString(StyleHeader.Render("  Agent Teams") + "\n\n")
	if m.err != "" {
		sb.WriteString(StyleError.Render("  Error: "+m.err) + "\n\n")
	}
	if m.status != "" {
		sb.WriteString(StyleOK.Render("  "+m.status) + "\n\n")
	}
	if len(m.teams) == 0 {
		sb.WriteString(StyleMuted.Render("  No agent teams yet. Press n to create one.\n"))
	} else {
		sb.WriteString(StyleMuted.Render(fmt.Sprintf("  %-24s %-10s %-6s  %s", "Team", "Status", "Tools", "Description")) + "\n")
		sb.WriteString(StyleMuted.Render("  "+strings.Repeat("─", 68)) + "\n")
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
			if len(desc) > 28 {
				desc = desc[:25] + "…"
			}
			var status string
			if team.IsActive {
				status = StyleOK.Render("● active  ")
			} else {
				status = StyleMuted.Render("○ inactive")
			}
			label := name
			if i == m.teamCursor {
				label = StylePrimary().Render(name)
			}
			sb.WriteString(fmt.Sprintf("%s%-22s %s %-6d  %s\n",
				cursor, label, status, len(team.PreApprovedToolNames), desc))
		}
		if m.teamCursor < len(m.teams) {
			team := m.teams[m.teamCursor]
			if len(team.PreApprovedToolNames) > 0 {
				tools := strings.Join(team.PreApprovedToolNames, ", ")
				if len(tools) > 66 {
					tools = tools[:63] + "…"
				}
				sb.WriteString("\n  " + StyleMuted.Render("Tools: ") + tools + "\n")
			} else {
				sb.WriteString("\n  " + StyleWarning.Render("No tools scoped — press t to assign tools") + "\n")
			}
		}
	}
	sb.WriteString("\n" + StyleHelp.Render("  ↑↓/j/k: select  enter: detail  n/c: new  t/s: tools  p: proposals  r: refresh"))
	return sb.String()
}

func (m AgentsModel) viewDetail() string {
	var sb strings.Builder
	sb.WriteString(StyleHeader.Render("  Team Details") + "\n\n")

	// Find the team.
	var team *api.AgentTeam
	for i := range m.teams {
		if m.teams[i].ID == m.detailTeamID {
			team = &m.teams[i]
			break
		}
	}
	if team == nil {
		sb.WriteString(StyleError.Render("  Team not found.") + "\n")
		sb.WriteString("\n" + StyleHelp.Render("  esc: back"))
		return sb.String()
	}

	if m.err != "" {
		sb.WriteString(StyleError.Render("  Error: "+m.err) + "\n\n")
	}
	if m.status != "" {
		sb.WriteString(StyleOK.Render("  "+m.status) + "\n\n")
	}

	sb.WriteString(fmt.Sprintf("  %s: %s\n", StylePrimary().Render("Name"), team.Name))
	sb.WriteString(fmt.Sprintf("  %s: %s\n", StyleMuted.Render("Description"), team.Description))
	sb.WriteString(fmt.Sprintf("  %s: ", StyleMuted.Render("Status")))
	if team.IsActive {
		sb.WriteString(StyleOK.Render("Active") + "\n")
	} else {
		sb.WriteString(StyleMuted.Render("Inactive") + "\n")
	}
	if team.IsSystem {
		sb.WriteString(fmt.Sprintf("  %s: %s\n", StyleMuted.Render("Type"), StyleWarning.Render("System (immutable)")))
	} else {
		sb.WriteString(fmt.Sprintf("  %s: %s\n", StyleMuted.Render("Type"), StyleOK.Render("User-managed")))
	}

	if len(team.CustomAgentIDs) > 0 {
		sb.WriteString(fmt.Sprintf("  %s: %d agents\n", StyleMuted.Render("Agents"), len(team.CustomAgentIDs)))
		for _, aid := range team.CustomAgentIDs {
			sb.WriteString(fmt.Sprintf("    - %s\n", aid))
		}
	}

	sb.WriteString(fmt.Sprintf("  %s: %d tools\n", StyleMuted.Render("Tools"), len(team.PreApprovedToolNames)))
	for _, t := range team.PreApprovedToolNames {
		sb.WriteString(fmt.Sprintf("    %s\n", StyleCyan().Render("✓ "+t)))
	}

	sb.WriteString("\n" + StyleHelp.Render("  e: edit  t/s: tools  d: delete  esc: back"))
	return sb.String()
}

func (m AgentsModel) viewEditForm() string {
	var sb strings.Builder
	sb.WriteString(StyleHeader.Render("  Edit Team") + "\n\n")
	labels := []string{"Name", "Description"}
	for i, inp := range m.editInputs {
		label := labels[i]
		if i == m.editFocused {
			label = StyleWarning.Render("▶ " + label)
		} else {
			label = StyleMuted.Render("  " + label)
		}
		sb.WriteString(label + "\n")
		sb.WriteString("  " + inp.View() + "\n\n")
	}
	if m.err != "" {
		sb.WriteString(StyleError.Render("  "+m.err) + "\n\n")
	}
	if m.loading {
		sb.WriteString(StyleMuted.Render("  Saving…") + "\n")
	}
	sb.WriteString("\n" + StyleHelp.Render("  Tab/↑↓: next  enter: save  esc: cancel"))
	return sb.String()
}

func (m AgentsModel) viewDeleteConfirm() string {
	var sb strings.Builder
	sb.WriteString(StyleHeader.Render("  Delete Team") + "\n\n")
	for _, t := range m.teams {
		if t.ID == m.detailTeamID {
			sb.WriteString(StyleWarning.Render(fmt.Sprintf("  Are you sure you want to delete \"%s\"?", t.Name)) + "\n\n")
			break
		}
	}
	sb.WriteString(StyleError.Render("  This action cannot be undone.") + "\n\n")
	sb.WriteString(StyleHelp.Render("  y: confirm delete  n/esc: cancel"))
	return sb.String()
}

func (m AgentsModel) viewProposals() string {
	var sb strings.Builder
	sb.WriteString(StyleHeader.Render("  Pending Proposals") + "\n\n")
	if m.err != "" {
		sb.WriteString(StyleError.Render("  Error: "+m.err) + "\n\n")
	}
	if m.status != "" {
		sb.WriteString(StyleOK.Render("  "+m.status) + "\n\n")
	}
	if len(m.proposals) == 0 {
		sb.WriteString(StyleMuted.Render("  No pending proposals.") + "\n")
	} else {
		sb.WriteString(StyleMuted.Render(fmt.Sprintf("  %-4s %-20s %-12s  %s", " ", "Proposal", "Action", "Created")) + "\n")
		sb.WriteString(StyleMuted.Render("  "+strings.Repeat("─", 60)) + "\n")
		for i, p := range m.proposals {
			cursor := "   "
			if i == m.proposalCursor {
				cursor = StyleWarning.Render(" ▶ ")
			}
			pid := p.ProposalID
			if len(pid) > 18 {
				pid = pid[:15] + "…"
			}
			action := p.ActionType
			if len(action) > 10 {
				action = action[:7] + "…"
			}
			created := p.CreatedAt
			if len(created) > 10 {
				created = created[:10]
			}
			sb.WriteString(fmt.Sprintf("%s%-18s %-12s  %s\n", cursor, pid, action, created))
		}
	}
	sb.WriteString("\n" + StyleHelp.Render("  ↑↓/j/k: move  enter: review  r: refresh  esc: back"))
	return sb.String()
}

func (m AgentsModel) viewProposalDetail() string {
	var sb strings.Builder
	sb.WriteString(StyleHeader.Render("  Proposal Detail") + "\n\n")
	if m.proposalCursor >= len(m.proposals) {
		sb.WriteString(StyleError.Render("  Proposal not found.") + "\n")
		sb.WriteString("\n" + StyleHelp.Render("  esc: back"))
		return sb.String()
	}
	p := m.proposals[m.proposalCursor]
	sb.WriteString(fmt.Sprintf("  %s: %s\n", StyleMuted.Render("ID"), p.ProposalID))
	sb.WriteString(fmt.Sprintf("  %s: %s\n", StyleMuted.Render("Action"), StylePrimary().Render(p.ActionType)))
	sb.WriteString(fmt.Sprintf("  %s: %s\n", StyleMuted.Render("Proposer"), p.Proposer))
	sb.WriteString(fmt.Sprintf("  %s: %s\n", StyleMuted.Render("Created"), p.CreatedAt))
	sb.WriteString(fmt.Sprintf("  %s: %v\n", StyleMuted.Render("Details"), p.Params))
	if m.loading {
		sb.WriteString("\n" + StyleMuted.Render("  Processing…"))
	} else {
		sb.WriteString("\n" + StyleHelp.Render("  y: approve  n: reject  esc: back"))
	}
	return sb.String()
}

func (m AgentsModel) viewCreateForm() string {
	var sb strings.Builder
	sb.WriteString(StyleHeader.Render("  New Agent Team") + "\n\n")
	labels := []string{"Name", "Description", "Specification (sent to IO)"}
	hints := []string{
		"Team identifier",
		"Brief summary of the team's role",
		"Natural language — IO blueprints agents and selects tools from this.",
	}
	for i, inp := range m.inputs {
		label := labels[i]
		if i == m.focused {
			label = StyleWarning.Render("▶ " + label)
		} else {
			label = StyleMuted.Render("  " + label)
		}
		sb.WriteString(label + "\n")
		sb.WriteString("  " + inp.View() + "\n")
		sb.WriteString(StyleMuted.Render("  "+hints[i]) + "\n\n")
	}
	if m.err != "" {
		sb.WriteString(StyleError.Render("  "+m.err) + "\n\n")
	}
	if m.status != "" {
		sb.WriteString(StyleOK.Render("  "+m.status) + "\n")
	}
	if m.loading {
		sb.WriteString(StyleMuted.Render("  Creating team…") + "\n")
	}
	sb.WriteString("\n" + StyleHelp.Render("  Tab/↑↓: next  shift+tab/↑: prev  enter: next/submit  esc: cancel"))
	return sb.String()
}

func (m AgentsModel) viewToolScope() string {
	var sb strings.Builder

	teamName := m.scopingTeamID
	for _, t := range m.teams {
		if t.ID == m.scopingTeamID {
			teamName = t.Name
			break
		}
	}

	sb.WriteString(StyleHeader.Render(fmt.Sprintf("  Scope Tools — %s", teamName)) + "\n\n")

	if m.status != "" {
		sb.WriteString(StyleOK.Render("  "+m.status) + "\n\n")
	}
	if m.err != "" {
		sb.WriteString(StyleError.Render("  Error: "+m.err) + "\n\n")
	}

	selected := len(m.collectSelected())
	sb.WriteString(StyleMuted.Render(fmt.Sprintf("  %d tool(s) selected\n\n", selected)))

	if m.toolsLoading {
		sb.WriteString(StyleMuted.Render("  Loading tools…\n"))
	} else if len(m.availableTools) == 0 {
		sb.WriteString(StyleMuted.Render("  No tools available.\n"))
	} else {
		sb.WriteString(StyleMuted.Render(fmt.Sprintf("  %-3s %-24s %-12s  %s", " ", "Tool", "Category", "Description")) + "\n")
		sb.WriteString(StyleMuted.Render("  "+strings.Repeat("─", 68)) + "\n")

		for i, tool := range m.availableTools {
			cursor := "  "
			if i == m.toolCursor {
				cursor = StyleWarning.Render("▶ ")
			}
			checkbox := "[ ]"
			if m.selectedTools[tool.Name] {
				checkbox = StyleOK.Render("[✓]")
			}

			name := tool.Name
			if len(name) > 22 {
				name = name[:19] + "…"
			}
			cat := tool.Category
			if len(cat) > 10 {
				cat = cat[:7] + "…"
			}
			desc := tool.Description
			if len(desc) > 28 {
				desc = desc[:25] + "…"
			}

			var statusDot string
			if tool.Status == "connected" {
				statusDot = StyleOK.Render("●")
			} else {
				statusDot = StyleMuted.Render("○")
			}

			row := fmt.Sprintf("%s%s %s %-24s %-12s  %s", cursor, checkbox, statusDot, name, cat, desc)
			if i == m.toolCursor {
				sb.WriteString(StyleWarning.Render(row) + "\n")
			} else {
				sb.WriteString(row + "\n")
			}
		}
	}

	if m.loading {
		sb.WriteString("\n" + StyleMuted.Render("  Saving…\n"))
	}
	sb.WriteString("\n" + StyleHelp.Render("  ↑↓/j/k: move  space: toggle  a: all  A: none  enter: save  esc: back"))
	return sb.String()
}

// ── Decode helpers ────────────────────────────────────────────────────────────

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
		if v, ok := m["isActive"].(bool); ok {
			t.IsActive = v
		}
		if v, ok := m["isSystemTeam"].(bool); ok {
			t.IsSystem = v
		}
		if raw, ok := m["customAgentIDs"]; ok {
			if ids, ok := raw.([]interface{}); ok {
				for _, id := range ids {
					if s, ok := id.(string); ok {
						t.CustomAgentIDs = append(t.CustomAgentIDs, s)
					}
				}
			}
		}
		if raw, ok := m["preApprovedToolNames"]; ok {
			if tools, ok := raw.([]interface{}); ok {
				for _, tool := range tools {
					if s, ok := tool.(string); ok {
						t.PreApprovedToolNames = append(t.PreApprovedToolNames, s)
					}
				}
			}
		}
		out = append(out, t)
	}
	return out
}

func decodeMCPTools(raw interface{}) []api.MCPTool {
	slice, ok := raw.([]interface{})
	if !ok {
		return nil
	}
	out := make([]api.MCPTool, 0, len(slice))
	for _, item := range slice {
		m, ok := item.(map[string]interface{})
		if !ok {
			continue
		}
		t := api.MCPTool{}
		if v, ok := m["name"].(string); ok {
			t.Name = v
		}
		if v, ok := m["description"].(string); ok {
			t.Description = v
		}
		if v, ok := m["category"].(string); ok {
			t.Category = v
		}
		if v, ok := m["status"].(string); ok {
			t.Status = v
		}
		out = append(out, t)
	}
	return out
}

func decodeProposals(raw interface{}) []api.Proposal {
	slice, ok := raw.([]interface{})
	if !ok {
		return nil
	}
	out := make([]api.Proposal, 0, len(slice))
	for _, item := range slice {
		m, ok := item.(map[string]interface{})
		if !ok {
			continue
		}
		p := api.Proposal{}
		if v, ok := m["proposalId"].(string); ok {
			p.ProposalID = v
		}
		if v, ok := m["actionType"].(string); ok {
			p.ActionType = v
		}
		if v, ok := m["proposer"].(string); ok {
			p.Proposer = v
		}
		if v, ok := m["createdAt"].(string); ok {
			p.CreatedAt = v
		}
		if v, ok := m["params"]; ok {
			p.Params = v
		}
		out = append(out, p)
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
