"""Proxy local do teste móvel: expõe apenas as rotas usadas pelo aplicativo."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.client import HTTPConnection
from urllib.parse import urlsplit, unquote


class AppProxy(BaseHTTPRequestHandler):
    def forward(self):
        path = unquote(urlsplit(self.path).path)
        allowed = path == "/" or any(path == root or path.startswith(root + "/") for root in ("/auth", "/my-groups", "/group-discovery"))
        if not allowed or ".." in path or self.command not in {"GET", "POST"}:
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        if length > 1024 * 1024:
            self.send_error(413)
            return
        upstream = HTTPConnection("127.0.0.1", 8000, timeout=30)
        try:
            body = self.rfile.read(length) if length else None
            headers = {k: v for k, v in self.headers.items() if k.lower() in {"authorization", "content-type", "accept"}}
            upstream.request(self.command, self.path, body=body, headers=headers)
            response = upstream.getresponse()
            data = response.read()
            self.send_response(response.status)
            self.send_header("Content-Type", response.getheader("Content-Type", "application/json"))
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
        except (OSError, TimeoutError):
            self.send_error(502)
        finally:
            upstream.close()

    do_GET = forward
    do_POST = forward

    def log_message(self, *_):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 8001), AppProxy).serve_forever()
