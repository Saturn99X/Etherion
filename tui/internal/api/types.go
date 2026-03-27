package api

// LoginResponse is returned by POST /api/tui/auth/login.
type LoginResponse struct {
	AccessToken     string `json:"access_token"`
	TokenType       string `json:"token_type"`
	UserID          string `json:"user_id"`
	Email           string `json:"email"`
	Name            string `json:"name"`
	TenantSubdomain string `json:"tenant_subdomain"`
}

// OAuthStatusResponse is returned by GET /oauth/silo/{provider}/status.
type OAuthStatusResponse struct {
	Connected bool   `json:"connected"`
	Provider  string `json:"provider"`
}

// HealthResponse is returned by GET /health.
type HealthResponse struct {
	Status string `json:"status"`
}

// GraphQLRequest is the standard GraphQL over HTTP request body.
type GraphQLRequest struct {
	Query     string                 `json:"query"`
	Variables map[string]interface{} `json:"variables,omitempty"`
}

// GraphQLResponse is the standard GraphQL over HTTP response body.
type GraphQLResponse struct {
	Data   map[string]interface{}   `json:"data"`
	Errors []map[string]interface{} `json:"errors,omitempty"`
}

// Thread represents a conversation thread.
type Thread struct {
	ID           string `json:"id"`
	Title        string `json:"title"`
	CreatedAt    string `json:"created_at"`
	MessageCount int    `json:"message_count"`
}

// Job represents an agent job from getJobHistory.
type Job struct {
	ID          string `json:"id"`
	Goal        string `json:"goal"`
	Status      string `json:"status"`
	CreatedAt   string `json:"createdAt"`
	CompletedAt string `json:"completedAt"`
	ThreadID    string `json:"threadId"`
}

// Message represents a single message within a thread.
type Message struct {
	ID        string `json:"messageId"`
	Role      string `json:"role"`
	Content   string `json:"content"`
	CreatedAt string `json:"createdAt"`
}

// Agent represents a single agent definition.
type Agent struct {
	ID          string `json:"id"`
	Name        string `json:"name"`
	Role        string `json:"role"`
	Description string `json:"description"`
}

// AgentTeam represents a named team of agents.
type AgentTeam struct {
	ID                   string   `json:"id"`
	Name                 string   `json:"name"`
	Description          string   `json:"description"`
	IsActive             bool     `json:"isActive"`
	IsSystem             bool     `json:"isSystemTeam"`
	CustomAgentIDs       []string `json:"customAgentIDs"`
	PreApprovedToolNames []string `json:"preApprovedToolNames"`
}

// KBSource represents a knowledge base integration source.
type KBSource struct {
	ServiceName   string   `json:"serviceName"`
	Status        string   `json:"status"`
	LastConnected string   `json:"lastConnected"`
	Capabilities  []string `json:"capabilities"`
}

// MCPTool represents an available tool that can be scoped to an agent team.
type MCPTool struct {
	Name        string   `json:"name"`
	Description string   `json:"description"`
	Category    string   `json:"category"`
	Status      string   `json:"status"`
	Capabilities []string `json:"capabilities"`
}

// APIError wraps an HTTP error from the backend.
type APIError struct {
	StatusCode int
	Body       string
}

func (e *APIError) Error() string {
	return "API error " + itoa(e.StatusCode) + ": " + e.Body
}

// itoa is a minimal int-to-string helper to avoid importing strconv in types.go.
func itoa(n int) string {
	if n == 0 {
		return "0"
	}
	neg := false
	if n < 0 {
		neg = true
		n = -n
	}
	buf := [20]byte{}
	pos := len(buf)
	for n > 0 {
		pos--
		buf[pos] = byte('0' + n%10)
		n /= 10
	}
	if neg {
		pos--
		buf[pos] = '-'
	}
	return string(buf[pos:])
}
