package api

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"
)

// Client is a typed HTTP client for the Etherion backend.
type Client struct {
	BaseURL string
	Token   string
	http    *http.Client
}

// New returns a new Client with a 120-second default timeout (LLM operations can be slow).
func New(baseURL, token string) *Client {
	return &Client{
		BaseURL: strings.TrimRight(baseURL, "/"),
		Token:   token,
		http:    &http.Client{Timeout: 120 * time.Second},
	}
}

// ---------- helpers ----------------------------------------------------------

func (c *Client) newRequest(ctx context.Context, method, path string, body interface{}) (*http.Request, error) {
	var buf io.Reader
	if body != nil {
		data, err := json.Marshal(body)
		if err != nil {
			return nil, err
		}
		buf = bytes.NewReader(data)
	}
	req, err := http.NewRequestWithContext(ctx, method, c.BaseURL+path, buf)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/json")
	if c.Token != "" {
		req.Header.Set("Authorization", "Bearer "+c.Token)
	}
	return req, nil
}

func (c *Client) do(req *http.Request, out interface{}) error {
	resp, err := c.http.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	raw, err := io.ReadAll(resp.Body)
	if err != nil {
		return err
	}

	if resp.StatusCode >= 400 {
		return &APIError{StatusCode: resp.StatusCode, Body: strings.TrimSpace(string(raw))}
	}

	if out != nil {
		return json.Unmarshal(raw, out)
	}
	return nil
}

// doWithRetry retries fn up to n times (n=1 means one attempt, no retry).
func doWithRetry[T any](n int, fn func() (T, error)) (T, error) {
	var zero T
	var lastErr error
	for i := 0; i < n; i++ {
		v, err := fn()
		if err == nil {
			return v, nil
		}
		lastErr = err
		// Don't retry client errors (4xx).
		if apiErr, ok := err.(*APIError); ok && apiErr.StatusCode < 500 {
			return zero, err
		}
	}
	return zero, lastErr
}

// ---------- auth -------------------------------------------------------------

// Login authenticates with email/password and returns the login response.
// The token is NOT automatically stored; callers must update config themselves.
func (c *Client) Login(ctx context.Context, email, password string) (LoginResponse, error) {
	return doWithRetry(1, func() (LoginResponse, error) {
		payload := map[string]string{"email": email, "password": password}
		req, err := c.newRequest(ctx, http.MethodPost, "/api/tui/auth/login", payload)
		if err != nil {
			return LoginResponse{}, err
		}
		// Login does not use the bearer token header.
		req.Header.Del("Authorization")
		var resp LoginResponse
		return resp, c.do(req, &resp)
	})
}

// ---------- OAuth ------------------------------------------------------------

// OAuthStatus checks whether a provider is connected for the current user.
func (c *Client) OAuthStatus(ctx context.Context, provider string) (OAuthStatusResponse, error) {
	return doWithRetry(2, func() (OAuthStatusResponse, error) {
		req, err := c.newRequest(ctx, http.MethodGet, "/oauth/silo/"+provider+"/status", nil)
		if err != nil {
			return OAuthStatusResponse{}, err
		}
		var resp OAuthStatusResponse
		return resp, c.do(req, &resp)
	})
}

// StorePersonalToken stores a personal access token (or API key) for a provider.
// extra may contain provider-specific fields (e.g. "email", "domain" for Jira).
func (c *Client) StorePersonalToken(ctx context.Context, provider, token string, extra map[string]string) error {
	_, err := doWithRetry(2, func() (struct{}, error) {
		payload := map[string]interface{}{
			"token": token,
		}
		for k, v := range extra {
			payload[k] = v
		}
		req, err := c.newRequest(ctx, http.MethodPost, "/api/tui/oauth/token/"+provider, payload)
		if err != nil {
			return struct{}{}, err
		}
		return struct{}{}, c.do(req, nil)
	})
	return err
}

// StartOAuthFlow starts a browser-based OAuth2 flow and returns the authorize URL.
func (c *Client) StartOAuthFlow(ctx context.Context, provider string) (string, error) {
	return doWithRetry(2, func() (string, error) {
		req, err := c.newRequest(ctx, http.MethodGet, "/oauth/silo/"+provider+"/start", nil)
		if err != nil {
			return "", err
		}
		var resp struct {
			AuthorizeURL string `json:"authorize_url"`
			URL          string `json:"url"` // alternate key some providers use
		}
		if err := c.do(req, &resp); err != nil {
			return "", err
		}
		if resp.AuthorizeURL != "" {
			return resp.AuthorizeURL, nil
		}
		return resp.URL, nil
	})
}

// StartOAuthFlowWithShop starts a browser-based OAuth2 flow for shop-specific providers (Shopify).
func (c *Client) StartOAuthFlowWithShop(ctx context.Context, provider, shop string) (string, error) {
	return doWithRetry(2, func() (string, error) {
		req, err := c.newRequest(ctx, http.MethodGet, "/oauth/silo/"+provider+"/start?shop="+shop, nil)
		if err != nil {
			return "", err
		}
		var resp struct {
			AuthorizeURL string `json:"authorize_url"`
			URL          string `json:"url"`
		}
		if err := c.do(req, &resp); err != nil {
			return "", err
		}
		if resp.AuthorizeURL != "" {
			return resp.AuthorizeURL, nil
		}
		return resp.URL, nil
	})
}

// RevokeOAuth disconnects a provider from the current user.
func (c *Client) RevokeOAuth(ctx context.Context, provider string) error {
	_, err := doWithRetry(2, func() (struct{}, error) {
		req, err := c.newRequest(ctx, http.MethodPost, "/oauth/silo/"+provider+"/revoke", nil)
		if err != nil {
			return struct{}{}, err
		}
		return struct{}{}, c.do(req, nil)
	})
	return err
}

// ---------- GraphQL ----------------------------------------------------------

// GraphQL executes an arbitrary GraphQL query against the backend.
func (c *Client) GraphQL(ctx context.Context, query string, variables map[string]interface{}) (GraphQLResponse, error) {
	return doWithRetry(2, func() (GraphQLResponse, error) {
		payload := GraphQLRequest{Query: query, Variables: variables}
		req, err := c.newRequest(ctx, http.MethodPost, "/graphql", payload)
		if err != nil {
			return GraphQLResponse{}, err
		}
		var resp GraphQLResponse
		if err := c.do(req, &resp); err != nil {
			return GraphQLResponse{}, err
		}
		if len(resp.Errors) > 0 {
			msgs := make([]string, len(resp.Errors))
			for i, e := range resp.Errors {
				if msg, ok := e["message"].(string); ok {
					msgs[i] = msg
				} else {
					msgs[i] = fmt.Sprintf("%v", e)
				}
			}
			return resp, fmt.Errorf("GraphQL errors: %s", strings.Join(msgs, "; "))
		}
		return resp, nil
	})
}

// ---------- health -----------------------------------------------------------

// Health calls GET /health and returns an error if the server is unreachable or unhealthy.
func (c *Client) Health(ctx context.Context) error {
	_, err := doWithRetry(2, func() (HealthResponse, error) {
		req, err := c.newRequest(ctx, http.MethodGet, "/health", nil)
		if err != nil {
			return HealthResponse{}, err
		}
		var resp HealthResponse
		return resp, c.do(req, &resp)
	})
	return err
}
