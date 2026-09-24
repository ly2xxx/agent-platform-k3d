import json
import os
import time
import uuid
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler

AGENT_URL = os.environ.get("AGENT_ENDPOINT", "http://agent-1:8080")
LANGFUSE_HOST = os.environ.get("LANGFUSE_HOST", "http://langfuse-web:3000")

HTML_UI = """<!DOCTYPE html>
<html>
<head>
  <title>BeSA Multi-Agent Platform</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 2rem; }
    .container { max-width: 800px; margin: 0 auto; background: #1e293b; border-radius: 12px; padding: 2rem; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.5); }
    h1 { color: #38bdf8; margin-top: 0; }
    .status { display: inline-block; padding: 4px 10px; background: #065f46; color: #34d399; border-radius: 9999px; font-size: 0.85rem; margin-bottom: 1rem; }
    .chat-box { border: 1px solid #334155; border-radius: 8px; height: 320px; padding: 1rem; overflow-y: auto; background: #0f172a; margin-bottom: 1rem; font-family: monospace; white-space: pre-wrap; word-break: break-word; line-height: 1.5; }
    input[type="text"] { width: 75%; padding: 10px; border-radius: 6px; border: 1px solid #334155; background: #0f172a; color: #fff; box-sizing: border-box; }
    button { width: 22%; padding: 10px; border-radius: 6px; border: none; background: #0284c7; color: #fff; font-weight: bold; cursor: pointer; }
    button:hover { background: #0369a1; }
    button:disabled { background: #475569; cursor: not-allowed; }
  </style>
</head>
<body>
  <div class="container">
    <h1>BeSA Agent Platform</h1>
    <div class="status">&#9679; Cluster Active & Connected</div>
    <div class="chat-box" id="chat">Chat session initialized. Ask a query (e.g. order lookup or return)...</div>
    <div style="display: flex; justify-content: space-between;">
      <input type="text" id="query" placeholder="Type message..." value="I need a return for my order" onkeydown="if(event.key==='Enter')send()" />
      <button id="send-btn" onclick="send()">Send</button>
    </div>
  </div>
  <script>
    function addMessage(sender, text, color, meta) {
      const box = document.getElementById('chat');
      const msgDiv = document.createElement('div');
      msgDiv.style.marginTop = '12px';

      const senderSpan = document.createElement('strong');
      senderSpan.style.color = color;
      senderSpan.textContent = sender + ': ';
      msgDiv.appendChild(senderSpan);

      const contentSpan = document.createElement('span');
      contentSpan.textContent = text;
      msgDiv.appendChild(contentSpan);

      if (meta) {
        const metaDiv = document.createElement('div');
        metaDiv.style.color = '#64748b';
        metaDiv.style.fontSize = '0.75rem';
        metaDiv.style.marginTop = '2px';
        metaDiv.textContent = meta;
        msgDiv.appendChild(metaDiv);
      }

      box.appendChild(msgDiv);
      box.scrollTop = box.scrollHeight;
    }

    async function send() {
      const input = document.getElementById('query');
      const btn = document.getElementById('send-btn');
      const q = input.value.trim();
      if (!q) return;

      addMessage('User', q, '#38bdf8');
      input.value = '';
      btn.disabled = true;
      btn.textContent = 'Thinking...';

      try {
        const res = await fetch('/chat', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({query: q})
        });
        const data = await res.json();

        let text = '';
        let sender = 'Agent';
        if (data.response && data.response.response && data.response.response.specialist_response) {
          text = data.response.response.specialist_response;
          sender = 'Specialist Agent (A2A Route)';
        } else if (data.response && data.response.answer) {
          text = data.response.answer;
          sender = 'Customer Agent';
        } else if (data.response && typeof data.response === 'string') {
          text = data.response;
        } else {
          text = JSON.stringify(data.response || data, null, 2);
        }

        const meta = '[' + (data.trace_id || 'trace') + ' | Model: deepseek-v4-flash:cloud via LiteLLM]';
        addMessage(sender, text, '#34d399', meta);
      } catch (err) {
        addMessage('Error', String(err), '#f87171');
      } finally {
        btn.disabled = false;
        btn.textContent = 'Send';
      }
    }
  </script>
</body>
</html>
"""

class WebUIHandler(BaseHTTPRequestHandler):
    def _send(self, content, content_type='application/json', code=200):
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.end_headers()
        if isinstance(content, str):
            self.wfile.write(content.encode('utf-8'))
        else:
            self.wfile.write(content)

    def do_GET(self):
        if self.path in ['/healthz', '/health']:
            self._send(json.dumps({"status": "ok", "service": "webui"}), 'application/json')
        elif self.path in ['/', '/index.html']:
            self._send(HTML_UI, 'text/html')
        else:
            self._send(json.dumps({"error": "Not Found"}), 'application/json', code=404)

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length) if content_length > 0 else b'{}'
        body_str = body.decode('utf-8', errors='ignore').strip()

        payload = {}
        try:
            payload = json.loads(body_str)
        except Exception:
            import re
            m = re.search(r'query[:=]\s*["\']?([^"\'}]+)', body_str)
            if m:
                payload = {"query": m.group(1).strip()}
            else:
                payload = {"query": body_str.strip("{} ")}

        if self.path == '/chat':
            trace_id = f"trace-{uuid.uuid4().hex[:12]}"
            session_id = f"sess-{uuid.uuid4().hex[:8]}"
            query = payload.get("query", "")

            # Forward query to Agent-1
            agent_res = {}
            try:
                req_payload = json.dumps({"query": query, "session_id": session_id}).encode('utf-8')
                req = urllib.request.Request(
                    f"{AGENT_URL}/chat",
                    data=req_payload,
                    headers={'Content-Type': 'application/json'},
                    method='POST'
                )
                with urllib.request.urlopen(req, timeout=60) as resp:
                    agent_res = json.loads(resp.read().decode('utf-8'))
            except Exception as e:
                agent_res = {"error": f"Agent unreachable: {str(e)}"}

            # Return full structured token response including trace id for Langfuse validation
            response_data = {
                "trace_id": trace_id,
                "session_id": session_id,
                "status": "stream_complete",
                "response": agent_res
            }
            self._send(json.dumps(response_data), 'application/json')
        else:
            self._send(json.dumps({"error": "Unknown endpoint"}), 'application/json', code=404)

    def log_message(self, format, *args):
        return

if __name__ == '__main__':
    server = HTTPServer(('0.0.0.0', 8080), WebUIHandler)
    print("WebUI Server listening on port 8080...")
    server.serve_forever()
