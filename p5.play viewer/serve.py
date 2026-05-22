"""
Static file server + CORS proxy for studio.code.org.

The viewer is loaded from this server, and the iframe srcdoc loads p5.js,
p5.play.js, and (when importing) code.org animation images from this server.
Same-origin → no CORS issues, and we add Access-Control-Allow-Origin: * just
in case the iframe ever reads pixels from a tainted canvas.

Routes:
  GET /codeorg/<path>   -> https://studio.code.org/<path>  (with CORS headers)
  GET /<anything else>  -> static file from project root
"""

import http.server
import socketserver
import ssl
import urllib.request
import urllib.error
import sys

PORT = 8766
UPSTREAM = "https://studio.code.org"

# macOS Python's stdlib urllib doesn't read the system keychain. Use certifi
# if available; otherwise fall back to an unverified context (fine here —
# this is a localhost dev proxy that fetches public, read-only endpoints).
try:
    import certifi  # type: ignore
    _SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except Exception:
    _SSL_CTX = ssl._create_unverified_context()


class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/codeorg/"):
            self._proxy()
            return
        super().do_GET()

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()

    def _proxy(self):
        upstream_path = self.path[len("/codeorg") :]
        url = UPSTREAM + upstream_path
        req = urllib.request.Request(url, headers={"User-Agent": "p5play-viewer/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=15, context=_SSL_CTX) as resp:
                body = resp.read()
                ctype = resp.headers.get("Content-Type", "application/octet-stream")
                self.send_response(resp.status)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
        except urllib.error.HTTPError as e:
            body = e.read() if e.fp else b""
            self.send_response(e.code)
            self.send_header("Content-Type", e.headers.get("Content-Type", "text/plain"))
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            msg = f"Proxy error: {e}".encode()
            self.send_response(502)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(msg)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(msg)

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))


class ReusableTCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    with ReusableTCPServer(("", PORT), Handler) as httpd:
        print(f"Serving at http://localhost:{PORT}")
        httpd.serve_forever()
