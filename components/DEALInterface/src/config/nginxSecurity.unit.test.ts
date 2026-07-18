import { describe, expect, it } from "vitest";

import nginxConfig from "../../nginx.conf?raw";

describe("nginx security policy", () => {
  it("suppresses version disclosure and emits baseline response headers", () => {
    expect(nginxConfig).toContain("server_tokens off;");
    expect(nginxConfig).toContain("charset utf-8;");
    expect(nginxConfig).toContain('add_header X-Content-Type-Options "nosniff" always;');
    expect(nginxConfig).toContain('add_header X-Frame-Options "DENY" always;');
    expect(nginxConfig).toContain('add_header Referrer-Policy "no-referrer" always;');
    expect(nginxConfig).toContain(
      'add_header Permissions-Policy "camera=(), geolocation=(), microphone=(), payment=(), usb=()" always;',
    );
  });

  it("keeps the static SPA compatible while denying active third-party content", () => {
    const csp = nginxConfig.match(/add_header Content-Security-Policy "([^"]+)" always;/)?.[1];

    expect(csp).toBeDefined();
    expect(csp).toContain("default-src 'self'");
    expect(csp).toContain("script-src 'self'");
    expect(csp).toContain("style-src 'self' 'unsafe-inline'");
    expect(csp).toContain("connect-src 'self'");
    expect(csp).toContain("object-src 'none'");
    expect(csp).toContain("frame-ancestors 'none'");
  });
});
