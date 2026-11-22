import argparse
from http.server import ThreadingHTTPServer
from pathlib import Path

from . import profile
from .db import initialize
from .errors import Problem
from .http import Endpoint
from .service import Service


def main():
    parser = argparse.ArgumentParser(description=profile.TITLE)
    parser.add_argument('--port', type=int, default=profile.PORT)
    parser.add_argument('--db', type=Path, default=Path(f'{profile.PRODUCT}.sqlite3'))
    args = parser.parse_args()
    try:
        if not 0 <= args.port <= 65535:
            parser.error('端口超出范围')
        initialize(args.db, profile.PRODUCT)
        with ThreadingHTTPServer(('127.0.0.1', args.port), Endpoint) as server:
            server.service = Service(args.db, profile)
            print(f'http://127.0.0.1:{server.server_port}', flush=True)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
    except (OSError, Problem) as exc:
        parser.error(str(exc))


if __name__ == '__main__':
    main()
