package ui

import (
	"fmt"
	"os"
	"strings"

	"github.com/charmbracelet/bubbles/textinput"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/etherion-ai/etherion/tui/internal/config"
)

type envEntry struct {
	key        string
	value      string
	comment    string
	sensitive  bool
	section    string
}

type envViewMode int

const (
	envModeList  envViewMode = iota
	envModeEdit
)

var envVars = []envEntry{
	// ── Environment ──
	{"ENVIRONMENT", "development", "development or production", false, "Environment"},
	// ── Database ──
	{"DATABASE_URL", "", "PostgreSQL sync URL: postgresql+psycopg2://user:pass@host:port/db", true, "Database"},
	{"ASYNC_DATABASE_URL", "", "PostgreSQL async URL: postgresql+asyncpg://user:pass@host:port/db", true, "Database"},
	// ── Redis ──
	{"REDIS_URL", "redis://localhost:6379/0", "Redis connection URL with db number", true, "Redis"},
	{"CELERY_BROKER_URL", "redis://localhost:6379/0", "Celery broker (same as Redis URL)", true, "Redis"},
	// ── Object Storage ──
	{"STORAGE_BACKEND", "pg", "pg | minio | local | gcs", false, "Storage"},
	{"STORAGE_LOCAL_ROOT", "/tmp/etherion-storage", "Local file storage root path", false, "Storage"},
	{"MINIO_ENDPOINT", "http://localhost:9000", "MinIO endpoint URL", false, "Storage"},
	{"MINIO_ACCESS_KEY", "", "MinIO access key", true, "Storage"},
	{"MINIO_SECRET_KEY", "", "MinIO secret key", true, "Storage"},
	// ── API ──
	{"API_HOST", "0.0.0.0", "Host to bind API server to", false, "API"},
	{"API_PORT", "8080", "Port for API server", false, "API"},
	{"CORS_ORIGINS", "http://localhost:3000", "CORS allowed origins (comma-separated)", false, "API"},
	// ── Auth ──
	{"JWT_SECRET_KEY", "", "JWT signing key (use a strong random string)", true, "Auth"},
	{"JWT_ALGORITHM", "HS256", "JWT signing algorithm", false, "Auth"},
	{"JWT_EXPIRATION_HOURS", "168", "JWT token expiry in hours (default 7 days)", false, "Auth"},
	// ── LLM Providers ──
	{"ORCHESTRATOR_PROVIDER", "bedrock", "Provider for Platform Orchestrator: bedrock|gemini|openai|openrouter|anthropic", false, "LLM"},
	{"ORCHESTRATOR_MODEL", "fast", "Model tier for Orchestrator: fast|default|smart|model_name", false, "LLM"},
	{"SPECIALIST_PROVIDER", "bedrock", "Provider for Specialist agents", false, "LLM"},
	{"SPECIALIST_MODEL", "fast", "Model tier for Specialists: fast|default|smart|model_name", false, "LLM"},
	{"EMBEDDING_PROVIDER", "gemini", "Provider for embeddings", false, "LLM"},
	{"EMBEDDING_MODEL", "text-embedding-004", "Model for embeddings (1,536 dims)", false, "LLM"},
	{"AWS_ACCESS_KEY_ID", "", "AWS IAM access key (for Bedrock)", true, "LLM"},
	{"AWS_SECRET_ACCESS_KEY", "", "AWS IAM secret key (for Bedrock)", true, "LLM"},
	{"AWS_REGION", "us-west-2", "AWS region for Bedrock", false, "LLM"},
	{"AWS_SESSION_TOKEN", "", "AWS SSO session token (temporary credentials only)", true, "LLM"},
	{"GEMINI_API_KEY", "", "Google Gemini API key (get from https://aistudio.google.com/apikey)", true, "LLM"},
	{"OPENROUTER_API_KEY", "", "OpenRouter API key (get from https://openrouter.ai/keys)", true, "LLM"},
	{"OPENAI_API_KEY", "", "OpenAI API key (get from https://platform.openai.com/api-keys)", true, "LLM"},
	{"ANTHROPIC_API_KEY", "", "Anthropic API key (get from https://console.anthropic.com)", true, "LLM"},
	{"EXA_API_KEY", "", "Exa search API key (for web research, get from https://dashboard.exa.ai)", true, "LLM"},
	// ── Knowledge Base ──
	{"KB_VECTOR_BACKEND", "pgvector", "Vector backend: pgvector (only option currently)", false, "KB"},
	{"KB_EMBEDDING_DIM", "1536", "Embedding dimensions (1536 recommended)", false, "KB"},
	{"SKIP_EMBEDDING", "true", "Skip embedding generation during ingest (true|false)", false, "KB"},
	// ── Secrets ──
	{"SECRETS_BACKEND", "local", "Secrets backend: local | vault", false, "Secrets"},
	// ── Misc ──
	{"DISABLE_GCP_LOGGING", "1", "Disable Google Cloud Logging (1 = yes)", false, "Misc"},
	{"LOG_LEVEL", "INFO", "Logging level: DEBUG|INFO|WARNING|ERROR", false, "Misc"},
	{"ENABLE_EXECUTION_TRACE", "true", "Record execution traces (true|false)", false, "Misc"},
}

type EnvModel struct {
	mode    envViewMode
	cursor  int
	entries []envEntry

	input   textinput.Model
	loading bool
	status  string
	err     string

	cfg *config.Config
}

func NewEnvModel(cfg *config.Config) EnvModel {
	ti := textinput.New()
	ti.CharLimit = 200
	ti.Width = 60

	// Load current values from env
	entries := make([]envEntry, len(envVars))
	copy(entries, envVars)
	for i := range entries {
		if v := os.Getenv(entries[i].key); v != "" {
			entries[i].value = v
		}
	}

	return EnvModel{
		mode:    envModeList,
		entries: entries,
		input:   ti,
		cfg:     cfg,
	}
}

func (m EnvModel) Init() tea.Cmd { return nil }

func (m EnvModel) Update(msg tea.Msg) (EnvModel, tea.Cmd) {
	var cmds []tea.Cmd

	if m.mode == envModeEdit {
		switch msg := msg.(type) {
		case tea.KeyMsg:
			switch msg.String() {
			case "esc":
				m.mode = envModeList
				m.input.Blur()
				m.status = ""
			case "enter":
				key := m.entries[m.cursor].key
				val := m.input.Value()
				m.entries[m.cursor].value = val
				m.mode = envModeList
				m.input.Blur()
				m.status = fmt.Sprintf("✓ %s = %s (saved to session. Use etherion init to write to .env)", key, maskIfSensitive(m.entries[m.cursor].sensitive, val))
			default:
				var c tea.Cmd
				m.input, c = m.input.Update(msg)
				cmds = append(cmds, c)
			}
		}
		return m, tea.Batch(cmds...)
	}

	switch msg := msg.(type) {
	case tea.KeyMsg:
		switch msg.String() {
		case "up", "k":
			if m.cursor > 0 {
				m.cursor--
			}
		case "down", "j":
			if m.cursor < len(m.entries)-1 {
				m.cursor++
			}
		case "enter", "e":
			e := m.entries[m.cursor]
			m.input.SetValue(e.value)
			m.input.Focus()
			m.mode = envModeEdit
			m.status = fmt.Sprintf("Editing: %s — %s", e.key, e.comment[:60])
			return m, textinput.Blink
		}
	}
	return m, nil
}

func (m EnvModel) View() string {
	var sb strings.Builder
	sb.WriteString(StyleHeader.Render("  Environment Variables (.env)") + "\n")
	sb.WriteString(StyleMuted.Render("  Press Enter on a row to edit. Changes apply to session — restart API to take effect.") + "\n\n")

	if m.status != "" {
		sb.WriteString(StyleOK.Render("  "+m.status) + "\n\n")
	}
	if m.err != "" {
		sb.WriteString(StyleError.Render("  "+m.err) + "\n\n")
	}

	if m.mode == envModeEdit {
		sb.WriteString(StyleInput.Width(60).Render(m.input.View()) + "\n")
		sb.WriteString("\n" + StyleHelp.Render("  Enter: save  esc: cancel"))
		return sb.String()
	}

	currentSection := ""
	for i, e := range m.entries {
		if e.section != currentSection {
			if currentSection != "" {
				sb.WriteString("\n")
			}
			sb.WriteString(StyleCyan().Render(fmt.Sprintf("  ── %s ──", e.section)) + "\n")
			currentSection = e.section
		}

		cursor := "  "
		if i == m.cursor {
			cursor = StyleWarning.Render("▶ ")
		}

		dispVal := e.value
		if e.sensitive && dispVal != "" {
			if len(dispVal) > 4 {
				dispVal = dispVal[:2] + "…" + dispVal[len(dispVal)-2:]
			} else {
				dispVal = "••••"
			}
		} else if dispVal == "" {
			dispVal = StyleMuted.Render("(not set)")
		}

		keyDisplay := fmt.Sprintf("%-28s", e.key)
		sb.WriteString(fmt.Sprintf("%s%s = %s\n", cursor, keyDisplay, dispVal))
		sb.WriteString(StyleMuted.Render(fmt.Sprintf("     # %s\n", e.comment)))
	}

	sb.WriteString("\n" + StyleHelp.Render("  ↑↓/j/k: move  enter/e: edit  |  0-9: switch tabs"))
	sb.WriteString("\n" + StyleMuted.Render(fmt.Sprintf("  %d variables across %d sections", len(envVars), countSections(envVars))))
	return sb.String()
}

func maskIfSensitive(sensitive bool, val string) string {
	if !sensitive || len(val) <= 4 {
		return val
	}
	return val[:2] + "…" + val[len(val)-2:]
}

func countSections(entries []envEntry) int {
	s := map[string]bool{}
	for _, e := range entries {
		s[e.section] = true
	}
	return len(s)
}
