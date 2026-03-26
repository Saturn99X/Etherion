package ui

import (
	"strings"

	"github.com/charmbracelet/bubbles/viewport"
	tea "github.com/charmbracelet/bubbletea"
)

type LogsModel struct {
	viewport viewport.Model
	lines    []string
	follow   bool
}

func NewLogsModel() LogsModel {
	vp := viewport.New(80, 20)
	return LogsModel{viewport: vp, follow: true}
}

func (m *LogsModel) SetSize(w, h int) {
	m.viewport.Width = w
	m.viewport.Height = h - 3
}

func (m LogsModel) Init() tea.Cmd { return nil }

func (m LogsModel) Update(msg tea.Msg) (LogsModel, tea.Cmd) {
	switch msg := msg.(type) {
	case logAppendMsg:
		m.lines = append(m.lines, msg.line)
		// Keep last 2000 lines
		if len(m.lines) > 2000 {
			m.lines = m.lines[len(m.lines)-2000:]
		}
		m.viewport.SetContent(strings.Join(m.lines, "\n"))
		if m.follow {
			m.viewport.GotoBottom()
		}
		return m, nil

	case tea.KeyMsg:
		switch msg.String() {
		case "f":
			m.follow = !m.follow
		}
	}

	var cmd tea.Cmd
	m.viewport, cmd = m.viewport.Update(msg)
	return m, cmd
}

func (m LogsModel) View() string {
	followStatus := StyleMuted.Render("follow: off")
	if m.follow {
		followStatus = StyleOK.Render("follow: on")
	}
	header := StyleHeader.Render("  Logs") + "  " + followStatus + "\n"
	return header + m.viewport.View() + "\n" + StyleHelp.Render("  f: toggle follow  ↑↓/PgUp/PgDn: scroll")
}
