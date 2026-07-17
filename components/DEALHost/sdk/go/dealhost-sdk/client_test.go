package dealhostsdk

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestCreateToolSendsExpectedRequest(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			t.Fatalf("method = %s, want POST", r.Method)
		}
		if r.URL.Path != "/api/hosting/tools/" {
			t.Fatalf("path = %s, want /api/hosting/tools/", r.URL.Path)
		}
		if got := r.Header.Get("Accept"); got != "application/json" {
			t.Fatalf("Accept = %s, want application/json", got)
		}
		if got := r.Header.Get("Content-Type"); !strings.HasPrefix(got, "application/json") {
			t.Fatalf("Content-Type = %s, want application/json", got)
		}
		if got := r.Header.Get("Authorization"); got != "Bearer secret" {
			t.Fatalf("Authorization = %s, want Bearer secret", got)
		}

		var body map[string]any
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			t.Fatalf("decode body: %v", err)
		}
		if body["name"] != "Tool" || body["slug"] != "tool" || body["enabled"] != false {
			t.Fatalf("body = %#v", body)
		}

		w.Header().Set("Content-Type", "application/json")
		fmt.Fprint(w, `{"id":123}`)
	}))
	defer server.Close()

	client := NewClient(server.URL+"/", "secret")
	client.HTTP = server.Client()

	body, err := client.CreateTool("Tool", "tool", "Description", []int{1, 2}, false)
	if err != nil {
		t.Fatalf("CreateTool returned error: %v", err)
	}
	if string(body) != `{"id":123}` {
		t.Fatalf("body = %s, want {\"id\":123}", body)
	}
	if client.BaseURL != server.URL {
		t.Fatalf("BaseURL = %s, want %s", client.BaseURL, server.URL)
	}
}

func TestListApplicationsSerializesFilters(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			t.Fatalf("method = %s, want GET", r.Method)
		}
		if r.URL.Path != "/api/hosting/applications/" {
			t.Fatalf("path = %s, want /api/hosting/applications/", r.URL.Path)
		}
		if got := r.URL.Query().Get("enabled"); got != "true" {
			t.Fatalf("enabled query = %s, want true", got)
		}
		if got := r.URL.Query().Get("module_slug"); got != "analytics" {
			t.Fatalf("module_slug query = %s, want analytics", got)
		}
		if r.Header.Get("Content-Type") != "" {
			t.Fatalf("Content-Type = %s, want empty for GET", r.Header.Get("Content-Type"))
		}

		fmt.Fprint(w, `[]`)
	}))
	defer server.Close()

	enabled := true
	client := NewClient(server.URL, "")
	client.HTTP = server.Client()

	body, err := client.ListApplications(&enabled, "analytics")
	if err != nil {
		t.Fatalf("ListApplications returned error: %v", err)
	}
	if string(body) != `[]` {
		t.Fatalf("body = %s, want []", body)
	}
}

func TestRequestReturnsStatusError(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "bad request", http.StatusBadRequest)
	}))
	defer server.Close()

	client := NewClient(server.URL, "")
	client.HTTP = server.Client()

	_, err := client.ListTools(nil, "")
	if err == nil {
		t.Fatal("ListTools returned nil error")
	}
	if !strings.Contains(err.Error(), "status=400") {
		t.Fatalf("error = %q, want status=400", err.Error())
	}
}
