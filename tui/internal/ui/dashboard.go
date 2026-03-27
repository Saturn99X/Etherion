package ui

import (
	"fmt"
	"net"
	"os"
	"strings"
	"time"

	tea "github.com/charmbracelet/bubbletea"
)

type DashboardModel struct {
	entries []healthEntry
	env     map[string]string
	lastRun time.Time
}

func NewDashboardModel() DashboardModel {
	env := loadEnv()
	return DashboardModel{env: env}
}

func (m DashboardModel) Init() tea.Cmd {
	return doHealthCheck(m.env)
}

func (m DashboardModel) Update(msg tea.Msg) (DashboardModel, tea.Cmd) {
	switch msg := msg.(type) {
	case healthResultMsg:
		m.entries = msg.results
		m.lastRun = time.Now()
	}
	return m, nil
}

func (m DashboardModel) View() string {
	var sb strings.Builder
	sb.WriteString(StyleHeader.Render("  Platform Health") + "\n\n")

	if len(m.entries) == 0 {
		sb.WriteString(StyleMuted.Render("  Checking services…") + "\n")
		return sb.String()
	}

	for _, e := range m.entries {
		icon := StyleOK.Render(iconOK)
		if !e.ok {
			icon = StyleError.Render(iconFail)
		}
		detail := StyleMuted.Render(e.detail)
		if e.ms > 0 {
			detail = StyleMuted.Render(fmt.Sprintf("%s (%dms)", e.detail, e.ms))
		}
		sb.WriteString(fmt.Sprintf("  %s  %-14s %s\n", icon, e.name, detail))
	}

	if !m.lastRun.IsZero() {
		sb.WriteString("\n" + StyleMuted.Render(fmt.Sprintf("  Last checked: %s", m.lastRun.Format("15:04:05"))))
	}
	return sb.String()
}

func doHealthCheck(env map[string]string) tea.Cmd {
	return func() tea.Msg {
		results := []healthEntry{
			tcpCheck("PostgreSQL", env["DATABASE_URL"], "localhost:5432"),
			tcpCheck("Redis", env["REDIS_URL"], "localhost:6379"),
			tcpCheck("MinIO", env["MINIO_ENDPOINT"], "localhost:9000"),
			httpCheck("API", env),
		}
		return healthResultMsg{results: results}
	}
}

func tcpCheck(name, urlStr, fallback string) healthEntry {
	host := extractHost(urlStr, fallback)
	t0 := time.Now()
	conn, err := net.DialTimeout("tcp", host, 2*time.Second)
	ms := int(time.Since(t0).Milliseconds())
	if err != nil {
		return healthEntry{name: name, ok: false, detail: err.Error(), ms: ms}
	}
	conn.Close()
	return healthEntry{name: name, ok: true, detail: host, ms: ms}
}

func httpCheck(name string, env map[string]string) healthEntry {
	apiHost := env["API_HOST"]
	if apiHost == "" || apiHost == "0.0.0.0" || apiHost == "::" {
		apiHost = "localhost"
	}
	// Strip any scheme the env might already include.
	apiHost = stripScheme(apiHost)
	port := env["API_PORT"]
	if port == "" {
		port = "8080"
	}
	// Build plain host:port for TCP dial — never add port twice.
	tcpAddr := fmt.Sprintf("%s:%s", apiHost, port)
	t0 := time.Now()
	conn, err := net.DialTimeout("tcp", tcpAddr, 2*time.Second)
	ms := int(time.Since(t0).Milliseconds())
	if err != nil {
		return healthEntry{name: name, ok: false, detail: err.Error(), ms: ms}
	}
	conn.Close()
	return healthEntry{name: name, ok: true, detail: fmt.Sprintf("http://%s", tcpAddr), ms: ms}
}

func extractHost(rawURL, fallback string) string {
	if rawURL == "" {
		return fallback
	}
	// Strip scheme
	for _, s := range []string{"postgresql+psycopg2://", "postgresql+asyncpg://", "postgresql://", "postgres://", "redis://", "http://", "https://"} {
		if strings.HasPrefix(rawURL, s) {
			rawURL = rawURL[len(s):]
			break
		}
	}
	// user:pass@host:port/db → host:port
	if at := strings.Index(rawURL, "@"); at >= 0 {
		rawURL = rawURL[at+1:]
	}
	if slash := strings.Index(rawURL, "/"); slash >= 0 {
		rawURL = rawURL[:slash]
	}
	return rawURL
}

func stripScheme(url string) string {
	for _, s := range []string{"http://", "https://"} {
		if strings.HasPrefix(url, s) {
			return url[len(s):]
		}
	}
	return url
}

func loadEnv() map[string]string {
	env := make(map[string]string)
	// Try to read .env file
	data, err := os.ReadFile(".env")
	if err != nil {
		// Fall back to actual environment
		for _, k := range []string{"DATABASE_URL", "REDIS_URL", "MINIO_ENDPOINT", "API_HOST", "API_PORT"} {
			env[k] = os.Getenv(k)
		}
		return env
	}
	for _, line := range strings.Split(string(data), "\n") {
		line = strings.TrimSpace(line)
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		parts := strings.SplitN(line, "=", 2)
		if len(parts) == 2 {
			env[parts[0]] = parts[1]
		}
	}
	return env
}
