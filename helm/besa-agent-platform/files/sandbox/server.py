import json
from http.server import HTTPServer, BaseHTTPRequestHandler

class BrowserSandboxHandler(BaseHTTPRequestHandler):
    def _send_json(self, data, code=200):
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))

    def do_GET(self):
        if self.path in ['/json/version', '/version', '/json']:
            self._send_json({
                "Browser": "HeadlessChrome/128.0.0.0",
                "Protocol-Version": "1.3",
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 HeadlessChrome",
                "V8-Version": "12.8.374",
                "WebKit-Version": "537.36",
                "webSocketDebuggerUrl": "ws://0.0.0.0:9222/devtools/browser/sandbox-session-0"
            })
        elif self.path in ['/healthz', '/health']:
            self._send_json({"status": "ok", "service": "headless-browser"})
        else:
            self._send_json({"status": "sandbox-active", "path": self.path})

    def log_message(self, format, *args):
        return

if __name__ == '__main__':
    server = HTTPServer(('0.0.0.0', 9222), BrowserSandboxHandler)
    print("Headless Browser Sandbox listening on port 9222...")
    server.serve_forever()
