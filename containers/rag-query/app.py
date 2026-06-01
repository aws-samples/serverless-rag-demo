import json
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from query import rag_query

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

PORT = 8080


class RAGQueryHandler(BaseHTTPRequestHandler):

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

            try:
                result = rag_query(
                    query=body.get("query", ""),
                    user_email=body.get("user_email"),
                    search_scope=body.get("search_scope", "all"),
                    chat_history=body.get("chat_history", []),
                )
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"response": result}).encode())
            except Exception as e:
                logger.error(f"RAG query error: {e}")
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
    server = HTTPServer(("0.0.0.0", PORT), RAGQueryHandler)
    logger.info(f"RAG Query runtime listening on port {PORT}")
    server.serve_forever()
