"""Local JSON transport for 量块组合公差计算; only loopback is exposed."""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from . import search
from . import fit
from . import reservation


ROUTES = {
    '/stackfit/certificate-status': search.available,
    '/stackfit/stack-interval': fit.check,
    '/stackfit/conforming-stacks': search.recommend,
    '/stackfit/shared-reservation': reservation.plan,
}


def fields(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate_json_key')
        result[key] = value
    return result


def nonfinite(value):
    raise ValueError('nonfinite_json')


class Endpoint(BaseHTTPRequestHandler):
    def setup(self):
        self.request.settimeout(3)
        super().setup()

    def send_json(self, code, body):
        data = json.dumps(body, ensure_ascii=True, allow_nan=False, sort_keys=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        operation = ROUTES.get(self.path)
        if operation is None:
            self.send_json(404, {'error':'unknown_workflow'})
            return
        if self.headers.get_content_type() != 'application/json':
            self.send_json(415, {'error':'expected_json'})
            return
        if self.headers.get('Transfer-Encoding') or len(self.headers.get_all('Content-Length', [])) != 1:
            self.send_json(400, {'error':'expected_single_content_length'})
            return
        try:
            size = int(self.headers['Content-Length'])
        except ValueError:
            size = 0
        if not 1 <= size <= 65536:
            self.send_json(413, {'error':'payload_size'})
            return
        try:
            raw = self.rfile.read(size)
            if len(raw) != size:
                raise ValueError('truncated_json')
            doc = json.loads(raw.decode('utf-8'), object_pairs_hook=fields, parse_constant=nonfinite)
            if not isinstance(doc, dict):
                raise ValueError('expected_object')
            output = operation(doc)
        except (KeyError, TypeError, ValueError, OverflowError, RecursionError) as exc:
            self.send_json(400, {'error':str(exc) if type(exc) is ValueError and len(str(exc)) < 100 else 'invalid_input'})
            return
        except TimeoutError:
            self.send_json(408, {'error':'incomplete_body'})
            return
        self.send_json(200, output)

    def log_message(self, fmt, *args):
        pass


def server(port):
    return HTTPServer(('127.0.0.1', port), Endpoint)


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', default=8745, type=int)
    with server(parser.parse_args().port) as httpd:
        print(f'Listening on http://127.0.0.1:{httpd.server_port}', flush=True)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
