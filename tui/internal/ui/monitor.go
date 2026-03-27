package ui

import (
	"context"
	"fmt"
	"strings"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/etherion-ai/etherion/tui/internal/api"
)

// MonitorModel shows a job history table.
type MonitorModel struct {
	jobs      []api.Job
	cursor    int
	err       string
	apiClient *api.Client
}

func NewMonitorModel(apiClient *api.Client) MonitorModel {
	return MonitorModel{apiClient: apiClient}
}

func (m MonitorModel) Init() tea.Cmd { return nil }

func (m MonitorModel) Update(msg tea.Msg) (MonitorModel, tea.Cmd) {
	var cmds []tea.Cmd

	switch msg := msg.(type) {
	case tea.KeyMsg:
		switch msg.String() {
		case "up", "k":
			if m.cursor > 0 {
				m.cursor--
			}
		case "down", "j":
			if m.cursor < len(m.jobs)-1 {
				m.cursor++
			}
		case "r":
			cmds = append(cmds, m.loadJobs())
		}

	case graphqlResultMsg:
		if msg.tab != tabMonitor {
			break
		}
		if msg.err != nil {
			m.err = msg.err.Error()
			break
		}
		m.err = ""
		// getJobHistory returns { jobs: [...], totalCount: N, pageInfo: {...} }
		if hist, ok := msg.data["getJobHistory"].(map[string]interface{}); ok {
			if jobs, ok := hist["jobs"]; ok {
				m.jobs = decodeJobs(jobs)
			}
		}
	}

	return m, tea.Batch(cmds...)
}

func (m *MonitorModel) loadJobs() tea.Cmd {
	if m.apiClient == nil {
		return nil
	}
	client := m.apiClient
	return func() tea.Msg {
		q := `query { getJobHistory(limit: 50) { jobs { id goal status createdAt completedAt threadId } } }`
		resp, err := client.GraphQL(context.Background(), q, nil)
		return graphqlResultMsg{data: resp.Data, tab: tabMonitor, err: err}
	}
}

func (m MonitorModel) View() string {
	var sb strings.Builder
	sb.WriteString(StyleHeader.Render("  Job Monitor") + "\n\n")

	if m.apiClient == nil {
		sb.WriteString(StyleWarning.Render("  Connect to server first (tab 1)\n"))
		return sb.String()
	}

	if m.err != "" {
		sb.WriteString(StyleError.Render("  Error: "+m.err) + "\n\n")
	}

	if len(m.jobs) == 0 {
		sb.WriteString(StyleMuted.Render("  No jobs found. Press r to refresh.\n"))
	} else {
		sb.WriteString(StyleMuted.Render(
			fmt.Sprintf("  %-10s %-32s %-18s  %s",
				"Status", "Goal", "Started", "Completed")) + "\n")
		sb.WriteString(StyleMuted.Render("  "+strings.Repeat("─", 74)) + "\n")

		for i, j := range m.jobs {
			cursor := "   "
			if i == m.cursor {
				cursor = StyleWarning.Render(" ▶ ")
			}

			var statusIcon string
			switch j.Status {
			case "running":
				statusIcon = StyleWarning.Render("● running ")
			case "done", "completed":
				statusIcon = StyleOK.Render("✓ done    ")
			case "failed":
				statusIcon = StyleError.Render("✗ failed  ")
			default:
				statusIcon = StyleMuted.Render("○ " + j.Status)
			}

			goal := j.Goal
			if len(goal) > 30 {
				goal = goal[:27] + "…"
			}
			started := j.CreatedAt
			if len(started) > 16 {
				started = started[:16]
			}
			completed := j.CompletedAt
			if completed == "" {
				completed = "—"
			} else if len(completed) > 16 {
				completed = completed[:16]
			}

			row := fmt.Sprintf("%s%-12s %-32s %-18s  %s",
				cursor, statusIcon, goal, started, completed)
			if i == m.cursor {
				sb.WriteString(StyleWarning.Render(row) + "\n")
			} else {
				sb.WriteString(row + "\n")
			}
		}
	}

	sb.WriteString("\n" + StyleHelp.Render("  ↑↓/j/k: move  r: refresh"))
	return sb.String()
}
