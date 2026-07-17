package io.dealhost.sdk;

import java.io.IOException;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class DealHostClient {
    private final String baseUrl;
    private final String token;
    private final HttpClient http;

    public DealHostClient(String baseUrl, String token) {
        this.baseUrl = baseUrl.replaceAll("/$", "");
        this.token = token;
        this.http = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(30)).build();
    }

    public String createTool(String name, String slug, String description, List<Integer> moduleIds, boolean enabled)
            throws IOException, InterruptedException {
        return request(
                "POST",
                "/api/hosting/tools/",
                hostingPayload(name, slug, description, moduleIds, enabled),
                null
        );
    }

    public String createApplication(String name, String slug, String description, List<Integer> moduleIds, boolean enabled)
            throws IOException, InterruptedException {
        return request(
                "POST",
                "/api/hosting/applications/",
                hostingPayload(name, slug, description, moduleIds, enabled),
                null
        );
    }

    static String hostingPayload(
            String name,
            String slug,
            String description,
            List<Integer> moduleIds,
            boolean enabled
    ) {
        String json = String.format(
                "{\"name\":\"%s\",\"slug\":\"%s\",\"description\":\"%s\",\"module_ids\":%s,\"enabled\":%s}",
                escapeJsonString(name),
                escapeJsonString(slug),
                escapeJsonString(description),
                moduleIds == null ? "[]" : moduleIds.toString(),
                enabled
        );
        return json;
    }

    public String listTools(Boolean enabled, String moduleSlug) throws IOException, InterruptedException {
        return request("GET", "/api/hosting/tools/", null, Map.of(
                "enabled", enabled == null ? "" : enabled.toString(),
                "module_slug", moduleSlug == null ? "" : moduleSlug
        ));
    }

    public String listApplications(Boolean enabled, String moduleSlug) throws IOException, InterruptedException {
        return request("GET", "/api/hosting/applications/", null, Map.of(
                "enabled", enabled == null ? "" : enabled.toString(),
                "module_slug", moduleSlug == null ? "" : moduleSlug
        ));
    }

    private String request(String method, String path, String jsonBody, Map<String, String> query)
            throws IOException, InterruptedException {
        String fullUrl = buildUrl(path, query);
        HttpRequest.Builder builder = HttpRequest.newBuilder()
                .uri(URI.create(fullUrl))
                .timeout(Duration.ofSeconds(30))
                .header("Accept", "application/json");

        if (token != null && !token.isBlank()) {
            builder.header("Authorization", "Bearer " + token);
        }

        if (jsonBody != null) {
            builder.header("Content-Type", "application/json");
            builder.method(method, HttpRequest.BodyPublishers.ofString(jsonBody));
        } else {
            builder.method(method, HttpRequest.BodyPublishers.noBody());
        }

        HttpResponse<String> response = http.send(builder.build(), HttpResponse.BodyHandlers.ofString());
        if (response.statusCode() >= 400) {
            throw new IOException("dealhost request failed: status=" + response.statusCode() + " body=" + response.body());
        }
        return response.body();
    }

    private String buildUrl(String path, Map<String, String> query) {
        if (query == null || query.isEmpty()) {
            return baseUrl + path;
        }
        String q = query.entrySet().stream()
                .filter(e -> e.getValue() != null && !e.getValue().isBlank())
                .map(e -> URLEncoder.encode(e.getKey(), StandardCharsets.UTF_8)
                        + "=" + URLEncoder.encode(e.getValue(), StandardCharsets.UTF_8))
                .collect(Collectors.joining("&"));
        if (q.isBlank()) {
            return baseUrl + path;
        }
        return baseUrl + path + "?" + q;
    }

    private static String escapeJsonString(String value) {
        StringBuilder escaped = new StringBuilder(value.length());
        for (int index = 0; index < value.length(); index++) {
            char character = value.charAt(index);
            switch (character) {
                case '\\':
                    escaped.append("\\\\");
                    break;
                case '"':
                    escaped.append("\\\"");
                    break;
                case '\b':
                    escaped.append("\\b");
                    break;
                case '\f':
                    escaped.append("\\f");
                    break;
                case '\n':
                    escaped.append("\\n");
                    break;
                case '\r':
                    escaped.append("\\r");
                    break;
                case '\t':
                    escaped.append("\\t");
                    break;
                default:
                    if (character < 0x20) {
                        escaped.append(String.format("\\u%04x", (int) character));
                    } else {
                        escaped.append(character);
                    }
            }
        }
        return escaped.toString();
    }
}
