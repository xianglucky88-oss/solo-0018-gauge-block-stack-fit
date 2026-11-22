"""Send the bundled synthetic input to an ephemeral local HTTP service."""
import argparse
from pathlib import Path
from threading import Thread
from urllib.request import ProxyHandler, Request, build_opener
from .http_api import ROUTES, server


def demo(route, filename):
    payload = Path(filename).read_bytes()
    with server(0) as listener:
        worker = Thread(target=listener.handle_request, daemon=True)
        worker.start()
        req = Request(f'http://127.0.0.1:{listener.server_port}{route}', data=payload,
                      headers={'Content-Type': 'application/json'})
        with build_opener(ProxyHandler({})).open(req, timeout=5) as response:
            print(response.read().decode('utf-8'))
        worker.join(timeout=4)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('route', choices=sorted(ROUTES))
    parser.add_argument('--input', default='examples/demo.json')
    args = parser.parse_args()
    demo(args.route, args.input)
