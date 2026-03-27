package ui

import (
	"context"
	"fmt"
	"strings"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/etherion-ai/etherion/tui/internal/api"
)

// ChatModel shows threads on the left and messages for the selected thread on the right.
type ChatModel struct {
	threads      []api.Thread
	messages     []api.Message
	threadCursor int
	msgCursor    int
	focusLeft    bool
	err          string
	apiClient    *api.Client
}

func NewChatModel(apiClient *api.Client) ChatModel {
	return ChatModel{focusLeft: true, apiClient: apiClient}
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
					cmds = append(cmds, m.loadMessages())
				}
			} else {
				if m.msgCursor > 0 {
					m.msgCursor--
				}
			}

		case "down", "j":
			if m.focusLeft {
				if m.threadCursor < len(m.threads)-1 {
					m.threadCursor++
					cmds = append(cmds, m.loadMessages())
				}
			} else {
				if m.msgCursor < len(m.messages)-1 {
					m.msgCursor++
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
		if threads, ok := msg.data["listThreads"]; ok {
			m.threads = decodeThreads(threads)
			if len(m.threads) > 0 {
				if m.threadCursor >= len(m.threads) {
					m.threadCursor = len(m.threads) - 1
				}
				cmds = append(cmds, m.loadMessages())
			}
		}
		if msgs, ok := msg.data["listMessages"]; ok {
			m.messages = decodeMessages(msgs)
			m.msgCursor = 0
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
		q := `query { listThreads { threadId title createdAt } }`
		resp, err := client.GraphQL(context.Background(), q, nil)
		return graphqlResultMsg{data: resp.Data, tab: tabChat, err: err}
	}
}

func (m *ChatModel) loadMessages() tea.Cmd {
	if m.apiClient == nil || len(m.threads) == 0 {
		return nil
	}
	client := m.apiClient
	threadID := m.threads[m.threadCursor].ID
	return func() tea.Msg {
		q := `query ListMessages($threadId: String!) { listMessages(threadId: $threadId, limit: 50) { messageId role content createdAt } }`
		vars := map[string]interface{}{"threadId": threadID}
		resp, err := client.GraphQL(context.Background(), q, vars)
		return graphqlResultMsg{data: resp.Data, tab: tabChat, err: err}
	}
}

func (m ChatModel) View() string {
	var sb strings.Builder
	sb.WriteString(StyleHeader.Render("  Chat — Threads & Messages") + "\n\n")

	if m.apiClient == nil {
		sb.WriteString(StyleWarning.Render("  Connect to server first (tab 1)\n"))
		return sb.String()
	}

	if m.err != "" {
		sb.WriteString(StyleError.Render("  Error: "+m.err) + "\n\n")
	}

	leftWidth := 28
	rightWidth := 44

	leftHeader := "  Threads"
	rightHeader := "  Messages"
	if len(m.threads) > 0 {
		t := m.threads[m.threadCursor]
		title := t.Title
		if len(title) > 20 {
			title = title[:17] + "…"
		}
		rightHeader = fmt.Sprintf("  %q", title)
	}

	lh := StyleMuted.Render(leftHeader)
	rh := StyleMuted.Render(rightHeader)
	if m.focusLeft {
		lh = StyleWarning.Render(leftHeader)
	} else {
		rh = StyleWarning.Render(rightHeader)
	}

	sb.WriteString(fmt.Sprintf("%-*s│  %s\n", leftWidth, lh, rh))
	sb.WriteString(StyleMuted.Render(strings.Repeat("─", leftWidth)+"┼"+strings.Repeat("─", rightWidth)) + "\n")

	threadLines := m.renderThreads(leftWidth)
	msgLines := m.renderMessages()

	maxRows := len(threadLines)
	if len(msgLines) > maxRows {
		maxRows = len(msgLines)
	}
	if maxRows == 0 {
		maxRows = 1
	}

	for i := 0; i < maxRows; i++ {
		left := ""
		right := ""
		if i < len(threadLines) {
			left = threadLines[i]
		}
		if i < len(msgLines) {
			right = msgLines[i]
		}
		sb.WriteString(fmt.Sprintf("%-*s│  %s\n", leftWidth, left, right))
	}

	if len(m.threads) == 0 {
		sb.WriteString(StyleMuted.Render("  No threads yet. Press r to refresh.\n"))
	}

	sb.WriteString("\n" + StyleHelp.Render("  h/l or ←/→: switch pane  ↑↓/j/k: move  r: refresh"))
	return sb.String()
}

func (m ChatModel) renderThreads(width int) []string {
	lines := make([]string, len(m.threads))
	for i, t := range m.threads {
		cursor := "   "
		if i == m.threadCursor && m.focusLeft {
			cursor = StyleWarning.Render(" ▶ ")
		}
		title := t.Title
		if title == "" {
			title = t.ID
		}
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

func (m ChatModel) renderMessages() []string {
	if len(m.messages) == 0 {
		if len(m.threads) > 0 {
			return []string{StyleMuted.Render("No messages")}
		}
		return nil
	}
	lines := make([]string, len(m.messages))
	for i, msg := range m.messages {
		cursor := "   "
		if i == m.msgCursor && !m.focusLeft {
			cursor = StyleWarning.Render(" ▶ ")
		}
		var roleLabel string
		switch msg.Role {
		case "user":
			roleLabel = StylePrimary().Render("you")
		case "assistant":
			roleLabel = StyleOK.Render("ai ")
		default:
			roleLabel = StyleMuted.Render(msg.Role)
		}
		content := msg.Content
		if len(content) > 36 {
			content = content[:33] + "…"
		}
		lines[i] = fmt.Sprintf("%s%s  %s", cursor, roleLabel, content)
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
		if v, ok := m["threadId"].(string); ok {
			t.ID = v
		}
		if v, ok := m["title"].(string); ok {
			t.Title = v
		}
		if v, ok := m["createdAt"].(string); ok {
			t.CreatedAt = v
		}
		out = append(out, t)
	}
	return out
}

func decodeMessages(raw interface{}) []api.Message {
	slice, ok := raw.([]interface{})
	if !ok {
		return nil
	}
	out := make([]api.Message, 0, len(slice))
	for _, item := range slice {
		m, ok := item.(map[string]interface{})
		if !ok {
			continue
		}
		msg := api.Message{}
		if v, ok := m["messageId"].(string); ok {
			msg.ID = v
		}
		if v, ok := m["role"].(string); ok {
			msg.Role = v
		}
		if v, ok := m["content"].(string); ok {
			msg.Content = v
		}
		if v, ok := m["createdAt"].(string); ok {
			msg.CreatedAt = v
		}
		out = append(out, msg)
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
		if v, ok := m["goal"].(string); ok {
			j.Goal = v
		}
		if v, ok := m["status"].(string); ok {
			j.Status = v
		}
		if v, ok := m["createdAt"].(string); ok {
			j.CreatedAt = v
		}
		if v, ok := m["completedAt"].(string); ok {
			j.CompletedAt = v
		}
		if v, ok := m["threadId"].(string); ok {
			j.ThreadID = v
		}
		out = append(out, j)
	}
	return out
}
