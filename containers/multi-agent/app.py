import json
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from graph import run_graph

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

PORT = 8080


class AgentCoreHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        if self.path == "/ping":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "healthy"}).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == "/invocations":
            content_length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(content_length))

            query = body.get("query", "")
            context = {
                "user_email": body.get("user_email"),
                "search_scope": body.get("search_scope", "all"),
                "connection_id": body.get("connection_id"),
            }

            try:
                result = run_graph(query, context)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"response": result}).encode())
            except Exception as e:
                logger.error(f"Invocation error: {e}")
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        logger.info(f"{self.address_string()} - {format % args}")


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", PORT), AgentCoreHandler)
    logger.info(f"Multi-Agent runtime listening on port {PORT}")
    server.serve_forever()
