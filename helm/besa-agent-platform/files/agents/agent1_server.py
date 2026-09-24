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
GATEWAY_URL = os.environ.get("AGENT_GATEWAY_URL", "http://agent-gateway:8000")
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

class Agent1Handler(BaseHTTPRequestHandler):
    def _send_json(self, data, code=200):
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))

    def do_GET(self):
        if self.path in ['/healthz', '/health']:
            self._send_json({"ok": True, "agent": "customer-agent", "tier": "agent-runtime"})
        elif self.path == '/status':
            self._send_json({
                "agent": "customer-agent",
                "upstream_litellm": LITELLM_URL,
                "model": LITELLM_MODEL,
                "upstream_gateway": GATEWAY_URL
            })
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

        # If user asks for returns or specialist topics, delegate via A2A Gateway
        if any(k in query.lower() for k in ["return", "rma", "specialist", "refund"]):
            try:
                req_payload = json.dumps(payload).encode('utf-8')
                req = urllib.request.Request(
                    f"{GATEWAY_URL}/a2a/route",
                    data=req_payload,
                    headers={'Content-Type': 'application/json'},
                    method='POST'
                )
                with urllib.request.urlopen(req, timeout=60) as resp:
                    res = json.loads(resp.read().decode('utf-8'))
                    self._send_json({"agent": "customer-agent", "routed_via": "gateway", "response": res})
                    return
            except Exception as e:
                self._send_json({"agent": "customer-agent", "gateway_error": str(e)}, code=502)
                return

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
                    mcp_info = f"\nOrder info from MCP: {resp.read().decode('utf-8')}"
            except Exception:
                pass

        sys_prompt = (
            "You are AnyCompany Shop Customer Service Agent. Assist customers politely and concisely "
            "with general support, product questions, and order inquiries."
        )
        llm_text = call_litellm(f"{query}{mcp_info}", sys_prompt)

        self._send_json({
            "agent": "customer-agent",
            "session_id": payload.get("session_id", "sess-default"),
            "answer": llm_text,
            "model": LITELLM_MODEL
        })

    def log_message(self, format, *args):
        return

if __name__ == '__main__':
    server = HTTPServer(('0.0.0.0', 8080), Agent1Handler)
    print("Customer Agent (agent-1) listening on port 8080...")
    server.serve_forever()
