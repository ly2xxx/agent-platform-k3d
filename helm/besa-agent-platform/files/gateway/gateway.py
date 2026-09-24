import json
import os
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler

AGENT2_URL = os.environ.get("AGENT2_URL", "http://agent-2:8080")
MCP_URL = os.environ.get("MCP_SERVER_URL", "http://mcp-server:8000")
LITELLM_URL = os.environ.get("LITELLM_BASE_URL", "http://litellm:4000")

class GatewayHandler(BaseHTTPRequestHandler):
    def _send_json(self, data, code=200):
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))

    def do_GET(self):
        if self.path in ['/healthz', '/health']:
            self._send_json({"status": "ok", "service": "agent-gateway"})
        elif self.path == '/status':
            self._send_json({
                "service": "agent-gateway",
                "routes": {
                    "agent-2": AGENT2_URL,
                    "mcp": MCP_URL,
                    "litellm": LITELLM_URL
                }
            })
        elif self.path == '/upstream/litellm':
            try:
                req = urllib.request.Request(f"{LITELLM_URL}/health/liveliness")
                with urllib.request.urlopen(req, timeout=5) as resp:
                    self._send_json({"upstream": "litellm", "status": resp.status})
            except Exception as e:
                self._send_json({"upstream": "litellm", "error": str(e)}, code=502)
        else:
            self._send_json({"error": "Not Found"}, code=404)

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length) if content_length > 0 else b'{}'

        if self.path == '/a2a/route' or self.path == '/chat':
            # Proxy to Agent 2 (Specialist Agent)
            try:
                req = urllib.request.Request(
                    f"{AGENT2_URL}/chat",
                    data=body,
                    headers={'Content-Type': 'application/json'},
                    method='POST'
                )
                with urllib.request.urlopen(req, timeout=60) as resp:
                    res_data = json.loads(resp.read().decode('utf-8'))
                    self._send_json(res_data, code=resp.status)
            except Exception as e:
                self._send_json({"error": f"A2A delegation failed: {str(e)}"}, code=502)

        elif self.path.startswith('/mcp/'):
            tool_name = self.path.replace('/mcp/', '')
            try:
                req = urllib.request.Request(
                    f"{MCP_URL}/tools/{tool_name}",
                    data=body,
                    headers={'Content-Type': 'application/json'},
                    method='POST'
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    res_data = json.loads(resp.read().decode('utf-8'))
                    self._send_json(res_data, code=resp.status)
            except Exception as e:
                self._send_json({"error": f"MCP proxy failed: {str(e)}"}, code=502)
        else:
            self._send_json({"error": "Unknown gateway route"}, code=404)

    def log_message(self, format, *args):
        return

if __name__ == '__main__':
    server = HTTPServer(('0.0.0.0', 8000), GatewayHandler)
    print("Agent Gateway listening on port 8000...")
    server.serve_forever()
