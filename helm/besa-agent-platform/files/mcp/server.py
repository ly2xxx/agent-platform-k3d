import json
from http.server import HTTPServer, BaseHTTPRequestHandler

ORDERS = {
    "ORD-12345": {
        "customer": "Jane Doe",
        "items": [{"name": "Laptop Pro 15", "qty": 1, "price": 1299.99}],
        "status": "shipped", "tracking": "1Z999AA10123456784", "estimated_delivery": "2025-04-12"
    },
    "ORD-67890": {
        "customer": "John Smith",
        "items": [{"name": "Wireless Mouse", "qty": 1, "price": 29.99}],
        "status": "delivered", "tracking": "1Z999AA10987654321", "estimated_delivery": "2025-04-08"
    },
    "ORD-11111": {
        "customer": "Alice Johnson",
        "items": [{"name": "Noise Cancelling Headphones", "qty": 1, "price": 249.99}],
        "status": "processing", "tracking": None, "estimated_delivery": "2025-04-15"
    }
}

INVENTORY = {
    "Laptop Pro 15": 23, "Wireless Mouse": 156, "USB-C Hub": 89,
    "Noise Cancelling Headphones": 45, "Mechanical Keyboard": 67
}

class MCPHandler(BaseHTTPRequestHandler):
    def _send_json(self, data, code=200):
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))

    def do_GET(self):
        if self.path in ['/healthz', '/health']:
            self._send_json({"status": "ok", "service": "mcp-server"})
        elif self.path == '/tools':
            self._send_json({
                "tools": [
                    {"name": "lookup_order", "description": "Look up order status by order ID"},
                    {"name": "check_inventory", "description": "Check stock for a product"},
                    {"name": "initiate_return", "description": "Initiate return for an order"}
                ]
            })
        else:
            self._send_json({"error": "Not Found"}, code=404)

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length) if content_length > 0 else b'{}'
        try:
            payload = json.loads(body.decode('utf-8'))
        except Exception:
            payload = {}

        if self.path == '/tools/lookup_order':
            order_id = payload.get('order_id', '').upper()
            order = ORDERS.get(order_id)
            if order:
                self._send_json({"order_id": order_id, **order})
            else:
                self._send_json({"error": f"Order {order_id} not found."}, code=404)
        elif self.path == '/tools/check_inventory':
            prod = payload.get('product_name', '')
            qty = INVENTORY.get(prod)
            if qty is not None:
                self._send_json({"product": prod, "in_stock": qty > 0, "quantity": qty})
            else:
                self._send_json({"error": f"Product {prod} not found."}, code=404)
        else:
            self._send_json({"error": "Unknown tool endpoint"}, code=404)

    def log_message(self, format, *args):
        # Suppress noisy request logging
        return

if __name__ == '__main__':
    server = HTTPServer(('0.0.0.0', 8000), MCPHandler)
    print("MCP Server listening on port 8000...")
    server.serve_forever()
