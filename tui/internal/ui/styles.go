package ui

import "github.com/charmbracelet/lipgloss"

// Tokyo Night palette
const (
	colorBg      = "#1a1b26"
	colorFg      = "#a9b1d6"
	colorPrimary = "#7aa2f7"
	colorGreen   = "#9ece6a"
	colorRed     = "#f7768e"
	colorYellow  = "#e0af68"
	colorCyan    = "#7dcfff"
	colorMuted   = "#565f89"
	colorBorder  = "#3b4261"
)

// Icons
const (
	iconOK      = "✓"
	iconFail    = "✗"
	iconPending = "…"
	iconArrow   = "→"
)

var (
	StyleBase = lipgloss.NewStyle().
		Foreground(lipgloss.Color(colorFg)).
		Background(lipgloss.Color(colorBg))

	StyleTabActive = lipgloss.NewStyle().
		Bold(true).
		Foreground(lipgloss.Color(colorBg)).
		Background(lipgloss.Color(colorPrimary)).
		Padding(0, 2)

	StyleTabInactive = lipgloss.NewStyle().
		Foreground(lipgloss.Color(colorMuted)).
		Background(lipgloss.Color(colorBg)).
		Padding(0, 2)

	StyleTabBar = lipgloss.NewStyle().
		BorderStyle(lipgloss.NormalBorder()).
		BorderBottom(true).
		BorderForeground(lipgloss.Color(colorBorder))

	StyleHeader = lipgloss.NewStyle().
		Bold(true).
		Foreground(lipgloss.Color(colorPrimary)).
		MarginBottom(1)

	StyleOK = lipgloss.NewStyle().
		Foreground(lipgloss.Color(colorGreen)).
		Bold(true)

	StyleError = lipgloss.NewStyle().
		Foreground(lipgloss.Color(colorRed)).
		Bold(true)

	StyleWarning = lipgloss.NewStyle().
		Foreground(lipgloss.Color(colorYellow))

	StyleMuted = lipgloss.NewStyle().
		Foreground(lipgloss.Color(colorMuted))

	StyleBorder = lipgloss.NewStyle().
		Border(lipgloss.RoundedBorder()).
		BorderForeground(lipgloss.Color(colorBorder)).
		Padding(1, 2)

	StyleInput = lipgloss.NewStyle().
		Foreground(lipgloss.Color(colorFg)).
		Border(lipgloss.NormalBorder()).
		BorderForeground(lipgloss.Color(colorPrimary)).
		Padding(0, 1)

	StyleHelp = lipgloss.NewStyle().
		Foreground(lipgloss.Color(colorMuted)).
		MarginTop(1)
)
