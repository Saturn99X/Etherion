package ui

import "time"

// lineMsg carries a line of output from a subprocess to a specific tab.
type lineMsg struct {
	line string
	tab  int
}

// cmdDoneMsg signals a subprocess completed.
type cmdDoneMsg struct {
	err error
	tab int
}

// logAppendMsg appends a line to the Logs tab.
type logAppendMsg struct {
	line string
}

// healthResultMsg carries results from a health check.
type healthResultMsg struct {
	results []healthEntry
}

type healthEntry struct {
	name   string
	ok     bool
	detail string
	ms     int
}

// tickMsg is a periodic timer tick.
type tickMsg struct {
	t time.Time
}

// ---------- auth messages ----------------------------------------------------

// loginResultMsg is sent after an attempted login.
type loginResultMsg struct {
	token string
	email string
	name  string
	err   error
}

// registerResultMsg is sent after a first-time account creation attempt.
type registerResultMsg struct {
	email string
	err   error
}

// ---------- OAuth messages ---------------------------------------------------

// oauthStatusMsg is sent after polling a provider's connection status.
type oauthStatusMsg struct {
	provider  string
	connected bool
	err       error
}

// oauthFlowStartedMsg is sent after the backend returns a browser authorize URL.
type oauthFlowStartedMsg struct {
	provider     string
	authorizeURL string
	err          error
}

// personalTokenSavedMsg is sent after a personal-token store attempt.
type personalTokenSavedMsg struct {
	provider string
	err      error
}

// oauthRevokedMsg is sent after a provider disconnect attempt.
type oauthRevokedMsg struct {
	provider string
	err      error
}

// ---------- GraphQL messages -------------------------------------------------

// graphqlResultMsg carries the result of a GraphQL query, tagged with the
// originating tab constant so the router can dispatch it correctly.
type graphqlResultMsg struct {
	data map[string]interface{}
	tab  int
	err  error
}
