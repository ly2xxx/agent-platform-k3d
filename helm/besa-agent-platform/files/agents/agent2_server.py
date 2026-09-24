import json
import os
import re
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler

LITELLM_URL = os.environ.get("LITELLM_BASE_URL", "http://litellm:4000")
LITELLM_MODEL = os.environ.get("LITELLM_MODEL", "deepseek-v4-flash:cloud")
LITELLM_API_KEY = os.environ.get("LITELLM_API_KEY")
if not LITELLM_API_KEY:
    raise SystemExit("LITELLM_API_KEY is not set. It comes from the agent-secret Secret.")
MCP_URL = os.environ.get("MCP_SERVER_URL", "http://mcp-server:8000")

def call_litellm(prompt, system_prompt):
    try:
        req_data = json.dumps({
            "model": LITELLM_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.3
        }).encode('utf-8')
        req = urllib.request.Request(
            f"{LITELLM_URL}/chat/completions",
            data=req_data,
            headers={
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {LITELLM_API_KEY}'
            },
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            res = json.loads(resp.read().decode('utf-8'))
            return res["choices"][0]["message"]["content"]
    except Exception as e:
        return f"(LiteLLM call failed: {e})"

class Agent2Handler(BaseHTTPRequestHandler):
    def _send_json(self, data, code=200):
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))

    def do_GET(self):
        if self.path in ['/healthz', '/health']:
            self._send_json({"ok": True, "agent": "specialist-agent", "tier": "agent-runtime"})
        elif self.path == '/status':
            self._send_json({"agent": "specialist-agent", "upstream_litellm": LITELLM_URL, "model": LITELLM_MODEL, "mcp_url": MCP_URL})
        else:
            self._send_json({"error": "Not Found"}, code=404)

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length) if content_length > 0 else b'{}'
        body_str = body.decode('utf-8', errors='ignore').strip()
        payload = {}
        try:
            payload = json.loads(body_str)
        except Exception:
            m = re.search(r'query[:=]\s*["\']?([^"\'}]+)', body_str)
            if m:
                payload = {"query": m.group(1).strip()}
            else:
                payload = {"query": body_str.strip("{} ")}

        query = payload.get("query", "")

        # Check for order lookup context via MCP tool
        order_match = re.search(r'ORD-\d+', query)
        mcp_info = ""
        if order_match:
            try:
                mcp_req = urllib.request.Request(
                    f"{MCP_URL}/tools/lookup_order",
                    data=json.dumps({"order_id": order_match.group(0)}).encode('utf-8'),
                    headers={'Content-Type': 'application/json'},
                    method='POST'
                )
                with urllib.request.urlopen(mcp_req, timeout=5) as resp:
                    mcp_info = f"\nOrder details from MCP tool: {resp.read().decode('utf-8')}"
            except Exception:
                pass

        sys_prompt = (
            "You are AnyCompany Shop Specialist Returns Agent. You handle returns, RMAs, refunds, "
            "and item condition assessments. If no order ID is provided, ask the customer for it. "
            "Explain our 30-day return policy and RMA procedure clearly and concisely."
        )
        llm_text = call_litellm(f"{query}{mcp_info}", sys_prompt)

        self._send_json({
            "agent": "specialist-agent",
            "status": "processed",
            "specialist_response": llm_text,
            "model": LITELLM_MODEL
        })

    def log_message(self, format, *args):
        return

if __name__ == '__main__':
    server = HTTPServer(('0.0.0.0', 8080), Agent2Handler)
    print("Specialist Agent (agent-2) listening on port 8080...")
    server.serve_forever()
