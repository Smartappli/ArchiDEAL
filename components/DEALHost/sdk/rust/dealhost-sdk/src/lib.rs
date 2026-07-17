use reqwest::blocking::Client;
use reqwest::header::{ACCEPT, AUTHORIZATION};
use serde_json::{json, Value};

#[derive(Debug, Clone)]
pub struct DealHostClient {
    base_url: String,
    token: Option<String>,
    http: Client,
}

impl DealHostClient {
    pub fn new(base_url: impl Into<String>, token: Option<String>) -> Self {
        Self {
            base_url: base_url.into().trim_end_matches('/').to_string(),
            token,
            http: Client::new(),
        }
    }

    fn request(
        &self,
        method: reqwest::Method,
        path: &str,
        body: Option<Value>,
    ) -> Result<Value, reqwest::Error> {
        let mut req = self
            .http
            .request(method, format!("{}{}", self.base_url, path))
            .header(ACCEPT, "application/json");

        if let Some(token) = &self.token {
            req = req.header(AUTHORIZATION, format!("Bearer {}", token));
        }
        if let Some(payload) = body {
            req = req.json(&payload);
        }

        req.send()?.error_for_status()?.json::<Value>()
    }

    pub fn create_tool(
        &self,
        name: &str,
        slug: &str,
        description: &str,
        module_ids: Vec<i64>,
        enabled: bool,
    ) -> Result<Value, reqwest::Error> {
        self.request(
            reqwest::Method::POST,
            "/api/hosting/tools/",
            Some(json!({
                "name": name,
                "slug": slug,
                "description": description,
                "module_ids": module_ids,
                "enabled": enabled
            })),
        )
    }

    pub fn create_application(
        &self,
        name: &str,
        slug: &str,
        description: &str,
        module_ids: Vec<i64>,
        enabled: bool,
    ) -> Result<Value, reqwest::Error> {
        self.request(
            reqwest::Method::POST,
            "/api/hosting/applications/",
            Some(json!({
                "name": name,
                "slug": slug,
                "description": description,
                "module_ids": module_ids,
                "enabled": enabled
            })),
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::{BufRead, BufReader, Read, Write};
    use std::net::{TcpListener, TcpStream};
    use std::sync::mpsc;
    use std::thread;

    #[derive(Debug)]
    struct CapturedRequest {
        start_line: String,
        headers: Vec<String>,
        body: String,
    }

    fn read_request(stream: &TcpStream) -> CapturedRequest {
        let mut reader = BufReader::new(stream.try_clone().expect("clone stream"));
        let mut start_line = String::new();
        reader.read_line(&mut start_line).expect("read start line");

        let mut headers = Vec::new();
        let mut content_length = 0usize;
        loop {
            let mut line = String::new();
            reader.read_line(&mut line).expect("read header");
            if line == "\r\n" {
                break;
            }
            let header = line.trim().to_ascii_lowercase();
            if let Some(value) = header.strip_prefix("content-length: ") {
                content_length = value.trim().parse().expect("parse content length");
            }
            headers.push(header);
        }

        let mut body = vec![0; content_length];
        reader.read_exact(&mut body).expect("read body");

        CapturedRequest {
            start_line: start_line.trim().to_string(),
            headers,
            body: String::from_utf8(body).expect("request body utf8"),
        }
    }

    fn respond(mut stream: TcpStream, status: &str, body: &str) {
        write!(
            stream,
            "HTTP/1.1 {status}\r\ncontent-type: application/json\r\ncontent-length: {}\r\n\r\n{body}",
            body.len()
        )
        .expect("write response");
    }

    fn run_server(
        status: &'static str,
        body: &'static str,
    ) -> (String, mpsc::Receiver<CapturedRequest>) {
        let listener = TcpListener::bind("127.0.0.1:0").expect("bind test server");
        let base_url = format!("http://{}", listener.local_addr().expect("local addr"));
        let (tx, rx) = mpsc::channel();

        thread::spawn(move || {
            let (stream, _) = listener.accept().expect("accept request");
            let captured = read_request(&stream);
            tx.send(captured).expect("send captured request");
            respond(stream, status, body);
        });

        (base_url, rx)
    }

    #[test]
    fn create_tool_sends_expected_request() {
        let (base_url, rx) = run_server("200 OK", r#"{"id":123}"#);
        let client = DealHostClient::new(format!("{}/", base_url), Some("secret".to_string()));

        let response = client
            .create_tool("Tool", "tool", "Description", vec![1, 2], false)
            .expect("create tool response");
        let request = rx.recv().expect("captured request");

        assert_eq!(response["id"].as_i64(), Some(123));
        assert_eq!(client.base_url, base_url);
        assert_eq!(request.start_line, "POST /api/hosting/tools/ HTTP/1.1");
        assert!(request
            .headers
            .iter()
            .any(|header| header == "accept: application/json"));
        assert!(request
            .headers
            .iter()
            .any(|header| header == "authorization: bearer secret"));
        assert!(request
            .headers
            .iter()
            .any(|header| header.starts_with("content-type: application/json")));
        assert!(request.body.contains(r#""name":"Tool""#));
        assert!(request.body.contains(r#""slug":"tool""#));
        assert!(request.body.contains(r#""module_ids":[1,2]"#));
        assert!(request.body.contains(r#""enabled":false"#));
    }

    #[test]
    fn create_application_returns_http_error_status() {
        let (base_url, rx) = run_server("400 Bad Request", r#"{"error":"bad request"}"#);
        let client = DealHostClient::new(base_url, None);

        let err = client
            .create_application("App", "app", "", vec![], true)
            .expect_err("expected status error");
        let request = rx.recv().expect("captured request");

        assert!(err.status().map_or(false, |status| status.as_u16() == 400));
        assert_eq!(
            request.start_line,
            "POST /api/hosting/applications/ HTTP/1.1"
        );
        assert!(!request
            .headers
            .iter()
            .any(|header| header.starts_with("authorization:")));
    }
}
