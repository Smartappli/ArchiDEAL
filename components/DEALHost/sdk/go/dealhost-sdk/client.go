package dealhostsdk

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"
)

type DealHostClient struct {
	BaseURL string
	Token   string
	HTTP    *http.Client
}

func NewClient(baseURL, token string) *DealHostClient {
	return &DealHostClient{
		BaseURL: strings.TrimRight(baseURL, "/"),
		Token:   token,
		HTTP:    &http.Client{Timeout: 30 * time.Second},
	}
}

func (c *DealHostClient) request(method, path string, body any, query map[string]string) ([]byte, error) {
	u, err := url.Parse(c.BaseURL + path)
	if err != nil {
		return nil, err
	}
	q := u.Query()
	for k, v := range query {
		if v != "" {
			q.Set(k, v)
		}
	}
	u.RawQuery = q.Encode()

	var reader io.Reader
	if body != nil {
		payload, err := json.Marshal(body)
		if err != nil {
			return nil, err
		}
		reader = bytes.NewBuffer(payload)
	}

	req, err := http.NewRequest(method, u.String(), reader)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Accept", "application/json")
	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	if c.Token != "" {
		req.Header.Set("Authorization", "Bearer "+c.Token)
	}

	resp, err := c.HTTP.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, err
	}
	if resp.StatusCode >= http.StatusBadRequest {
		return nil, fmt.Errorf("dealhost request failed: status=%d body=%s", resp.StatusCode, string(respBody))
	}
	return respBody, nil
}

func (c *DealHostClient) CreateTool(name, slug, description string, moduleIDs []int, enabled bool) ([]byte, error) {
	return c.request("POST", "/api/hosting/tools/", map[string]any{
		"name":        name,
		"slug":        slug,
		"description": description,
		"module_ids":  moduleIDs,
		"enabled":     enabled,
	}, nil)
}

func (c *DealHostClient) CreateApplication(name, slug, description string, moduleIDs []int, enabled bool) ([]byte, error) {
	return c.request("POST", "/api/hosting/applications/", map[string]any{
		"name":        name,
		"slug":        slug,
		"description": description,
		"module_ids":  moduleIDs,
		"enabled":     enabled,
	}, nil)
}

func (c *DealHostClient) ListTools(enabled *bool, moduleSlug string) ([]byte, error) {
	query := map[string]string{"module_slug": moduleSlug}
	if enabled != nil {
		query["enabled"] = fmt.Sprintf("%t", *enabled)
	}
	return c.request("GET", "/api/hosting/tools/", nil, query)
}

func (c *DealHostClient) ListApplications(enabled *bool, moduleSlug string) ([]byte, error) {
	query := map[string]string{"module_slug": moduleSlug}
	if enabled != nil {
		query["enabled"] = fmt.Sprintf("%t", *enabled)
	}
	return c.request("GET", "/api/hosting/applications/", nil, query)
}
