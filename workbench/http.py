from http.server import BaseHTTPRequestHandler
import sqlite3

from . import assets
from .codec import decode, encode
from .errors import Problem


class Endpoint(BaseHTTPRequestHandler):
    def setup(self):
        self.request.settimeout(5)
        super().setup()

    def _write(self, body, mime, status=200, attachment=None):
        self.send_response(status)
        self.send_header('Content-Type', f'{mime}; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        if attachment:
            self.send_header('Content-Disposition', f'attachment; filename="{attachment}"')
        self.end_headers()
        self.wfile.write(body)

    def _json(self, data, status=200, attachment=None):
        self._write(encode(data).encode('utf-8'), 'application/json', status, attachment)

    def _check_local(self):
        port = self.server.server_port
        hosts = self.headers.get_all('Host', [])
        if len(hosts) != 1 or hosts[0] not in (f'127.0.0.1:{port}', f'localhost:{port}'):
            raise Problem('local_host_only', 403)
        origins = self.headers.get_all('Origin', [])
        if origins and origins != [f'http://{hosts[0]}']:
            raise Problem('local_origin_only', 403)

    def _body(self):
        if self.headers.get_content_type() != 'application/json':
            raise Problem('expected_json', 415)
        lengths = self.headers.get_all('Content-Length', [])
        if self.headers.get('Transfer-Encoding') or len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdecimal():
            raise Problem('content_length')
        if len(lengths[0]) > 7 or not 0 < int(lengths[0]) <= 2_000_000:
            raise Problem('request_size', 413)
        size = int(lengths[0])
        raw = self.rfile.read(size)
        if len(raw) != size:
            raise Problem('incomplete_request', 408)
        try:
            value = decode(raw.decode('utf-8'))
        except (ValueError, RecursionError) as exc:
            raise Problem('invalid_json') from exc
        if not isinstance(value, dict):
            raise Problem('expected_object')
        return value

    def _serve(self, write):
        try:
            self._check_local()
            if write:
                self._json(self.server.service.post(self.path, self._body()))
            elif self.path.startswith('/api/'):
                data, filename = self.server.service.get(self.path)
                self._json(data, attachment=filename)
            else:
                body, mime = assets.get(self.path)
                self._write(body, mime)
        except Problem as exc:
            self._json(exc.body, exc.status)
        except sqlite3.OperationalError as exc:
            if getattr(exc, 'sqlite_errorcode', None) in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
                self._json({'error': 'database_busy'}, 503)
            else:
                self.log_error('%s', exc)
                self._json({'error': 'database_error'}, 500)
        except TimeoutError:
            self._json({'error': 'incomplete_request'}, 408)
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True

    def do_GET(self):
        self._serve(False)

    def do_POST(self):
        self._serve(True)
