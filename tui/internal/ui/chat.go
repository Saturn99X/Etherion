package ui

import (
	"context"
	"fmt"
	"strings"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/etherion-ai/etherion/tui/internal/api"
)

// ChatModel shows threads on the left and jobs for the selected thread on the right.
type ChatModel struct {
	threads        []api.Thread
	jobs           []api.Job
	threadCursor   int
	jobCursor      int
	focusLeft      bool // true = left pane focused
	err            string
	apiClient      *api.Client
}

func NewChatModel() ChatModel {
	return ChatModel{focusLeft: true}
}

func (m ChatModel) Init() tea.Cmd { return nil }

func (m ChatModel) Update(msg tea.Msg) (ChatModel, tea.Cmd) {
	var cmds []tea.Cmd

	switch msg := msg.(type) {
	case tea.KeyMsg:
		switch msg.String() {
		case "h", "left":
			m.focusLeft = true
		case "l", "right":
			m.focusLeft = false

		case "up", "k":
			if m.focusLeft {
				if m.threadCursor > 0 {
					m.threadCursor--
					cmds = append(cmds, m.loadJobs())
				}
			} else {
				if m.jobCursor > 0 {
					m.jobCursor--
				}
			}

		case "down", "j":
			if m.focusLeft {
				if m.threadCursor < len(m.threads)-1 {
					m.threadCursor++
					cmds = append(cmds, m.loadJobs())
				}
			} else {
				if m.jobCursor < len(m.jobs)-1 {
					m.jobCursor++
				}
			}

		case "r":
			cmds = append(cmds, m.loadThreads())
		}

	case graphqlResultMsg:
		if msg.tab != tabChat {
			break
		}
		if msg.err != nil {
			m.err = msg.err.Error()
			break
		}
		m.err = ""
		// Try to decode threads.
		if threads, ok := msg.data["threads"]; ok {
			m.threads = decodeThreads(threads)
			if len(m.threads) > 0 {
				if m.threadCursor >= len(m.threads) {
					m.threadCursor = len(m.threads) - 1
				}
				cmds = append(cmds, m.loadJobs())
			}
		}
		// Try to decode jobs.
		if jobs, ok := msg.data["jobs"]; ok {
			m.jobs = decodeJobs(jobs)
		}
	}

	return m, tea.Batch(cmds...)
}

func (m *ChatModel) loadThreads() tea.Cmd {
	if m.apiClient == nil {
		return nil
	}
	client := m.apiClient
	return func() tea.Msg {
		q := `query ListThreads { threads { id title created_at message_count } }`
		resp, err := client.GraphQL(context.Background(), q, nil)
		return graphqlResultMsg{data: resp.Data, tab: tabChat, err: err}
	}
}

func (m *ChatModel) loadJobs() tea.Cmd {
	if m.apiClient == nil || len(m.threads) == 0 {
		return nil
	}
	client := m.apiClient
	threadID := m.threads[m.threadCursor].ID
	return func() tea.Msg {
		q := `query ListJobs($threadId: ID!) { jobs(threadId: $threadId) { id status agent_team_name created_at } }`
		vars := map[string]interface{}{"threadId": threadID}
		resp, err := client.GraphQL(context.Background(), q, vars)
		return graphqlResultMsg{data: resp.Data, tab: tabChat, err: err}
	}
}

func (m ChatModel) View() string {
	var sb strings.Builder
	sb.WriteString(StyleHeader.Render("  Chat — Threads & Jobs") + "\n\n")

	if m.apiClient == nil {
		sb.WriteString(StyleWarning.Render("  Connect to server first (tab 1)\n"))
		return sb.String()
	}

	if m.err != "" {
		sb.WriteString(StyleError.Render("  Error: "+m.err) + "\n\n")
	}

	leftWidth := 28
	rightWidth := 44

	// Left pane header.
	leftHeader := "  Threads"
	rightHeader := "  Jobs"
	if len(m.threads) > 0 {
		rightHeader = fmt.Sprintf("  Jobs in %q", m.threads[m.threadCursor].Title)
	}

	lh := StyleMuted.Render(leftHeader)
	rh := StyleMuted.Render(rightHeader)
	if m.focusLeft {
		lh = StyleWarning.Render(leftHeader)
	} else {
		rh = StyleWarning.Render(rightHeader)
	}

	sb.WriteString(fmt.Sprintf("%-*s│  %s\n", leftWidth, lh, rh))
	sb.WriteString(StyleMuted.Render(strings.Repeat("─", leftWidth) + "┼" + strings.Repeat("─", rightWidth)) + "\n")

	// Render rows.
	threadLines := m.renderThreads(leftWidth)
	jobLines := m.renderJobs()

	maxRows := len(threadLines)
	if len(jobLines) > maxRows {
		maxRows = len(jobLines)
	}

	for i := 0; i < maxRows; i++ {
		left := ""
		right := ""
		if i < len(threadLines) {
			left = threadLines[i]
		}
		if i < len(jobLines) {
			right = jobLines[i]
		}
		sb.WriteString(fmt.Sprintf("%-*s│  %s\n", leftWidth, left, right))
	}

	if len(m.threads) == 0 {
		sb.WriteString(StyleMuted.Render("  No threads yet") + "\n")
	}

	sb.WriteString("\n" + StyleHelp.Render("  h/l or ←/→: switch pane  ↑↓/j/k: move  r: refresh"))
	return sb.String()
}

func (m ChatModel) renderThreads(width int) []string {
	lines := make([]string, len(m.threads))
	for i, t := range m.threads {
		cursor := "  "
		if i == m.threadCursor && m.focusLeft {
			cursor = StyleWarning.Render(" ▶ ")
		} else {
			cursor = "   "
		}
		title := t.Title
		if len(title) > width-6 {
			title = title[:width-9] + "…"
		}
		if i == m.threadCursor {
			lines[i] = cursor + StylePrimary().Render(title)
		} else {
			lines[i] = cursor + title
		}
	}
	return lines
}

func (m ChatModel) renderJobs() []string {
	lines := make([]string, len(m.jobs))
	for i, j := range m.jobs {
		cursor := "   "
		if i == m.jobCursor && !m.focusLeft {
			cursor = StyleWarning.Render(" ▶ ")
		}

		var statusIcon string
		switch j.Status {
		case "running":
			statusIcon = StyleWarning.Render("●")
		case "done", "completed":
			statusIcon = StyleOK.Render("✓")
		case "failed":
			statusIcon = StyleError.Render("✗")
		default:
			statusIcon = StyleMuted.Render("○")
		}

		team := j.AgentTeamName
		if len(team) > 16 {
			team = team[:13] + "…"
		}
		lines[i] = fmt.Sprintf("%s%s %-18s", cursor, statusIcon, team)
	}
	return lines
}

// ---------------------------------------------------------------------------
// Decode helpers
// ---------------------------------------------------------------------------

func decodeThreads(raw interface{}) []api.Thread {
	slice, ok := raw.([]interface{})
	if !ok {
		return nil
	}
	out := make([]api.Thread, 0, len(slice))
	for _, item := range slice {
		m, ok := item.(map[string]interface{})
		if !ok {
			continue
		}
		t := api.Thread{}
		if v, ok := m["id"].(string); ok {
			t.ID = v
		}
		if v, ok := m["title"].(string); ok {
			t.Title = v
		}
		if v, ok := m["created_at"].(string); ok {
			t.CreatedAt = v
		}
		if v, ok := m["message_count"].(float64); ok {
			t.MessageCount = int(v)
		}
		out = append(out, t)
	}
	return out
}

func decodeJobs(raw interface{}) []api.Job {
	slice, ok := raw.([]interface{})
	if !ok {
		return nil
	}
	out := make([]api.Job, 0, len(slice))
	for _, item := range slice {
		m, ok := item.(map[string]interface{})
		if !ok {
			continue
		}
		j := api.Job{}
		if v, ok := m["id"].(string); ok {
			j.ID = v
		}
		if v, ok := m["status"].(string); ok {
			j.Status = v
		}
		if v, ok := m["agent_team_name"].(string); ok {
			j.AgentTeamName = v
		}
		if v, ok := m["created_at"].(string); ok {
			j.CreatedAt = v
		}
		out = append(out, j)
	}
	return out
}
