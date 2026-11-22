"""Replaceable adapters for the reuse-eligibility contract.

The contract in tests/reuse_contract.py is written against the
ReuseAdapter interface only.  To bind the contract to another
implementation of the reuse decision, subclass ReuseAdapter, implement
the operations below, and reference the subclass from a new test
module — the contract itself does not change.

Every adapter exposes the three real workflows as acceptance controls
(``full_search`` and ``certificate_status``) plus a counter of how many
full searches were performed, so the contract can prove the reuse path
never calls the full search and relabels the outcome as reuse.
"""
import json
from threading import Thread
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener
from gauge import http_api, reuse, search


class AdapterRejected(Exception):
    """The adapter rejected the reuse-decision input as invalid."""


class ReuseAdapter:
    name = 'abstract'

    def start(self):
        """Acquire resources before the contract runs."""

    def stop(self):
        """Release resources after the contract runs."""

    def decide(self, previous, request):
        """The reuse decision under test."""
        raise NotImplementedError

    def full_search(self, request):
        """A real new request through the conforming-stacks workflow."""
        raise NotImplementedError

    def certificate_status(self, request):
        """A real new request through the certificate-status workflow."""
        raise NotImplementedError

    def full_search_calls(self):
        """How many full searches this process has performed so far."""
        raise NotImplementedError

    def reset_counters(self):
        """Reset instrumentation before a measurement."""


class InProcessAdapter(ReuseAdapter):
    """Drives gauge.reuse.decide directly; the real search and status
    workflows serve as acceptance controls."""

    name = 'in-process'

    def start(self):
        self._calls = 0
        self._original = search.recommend

        def counted(doc):
            self._calls += 1
            return self._original(doc)

        search.recommend = counted

    def stop(self):
        search.recommend = self._original

    def decide(self, previous, request):
        try:
            return reuse.decide({'previous': previous, 'request': request})
        except (KeyError, TypeError, ValueError) as exc:
            raise AdapterRejected(str(exc)) from exc

    def full_search(self, request):
        return search.recommend(request)

    def certificate_status(self, request):
        return search.available(request)

    def full_search_calls(self):
        return self._calls

    def reset_counters(self):
        self._calls = 0


class HttpAdapter(ReuseAdapter):
    """Drives the same decision over the loopback HTTP service, with the
    full-search route instrumented server-side."""

    name = 'http'

    def start(self):
        self._calls = 0
        self._route_original = http_api.ROUTES['/stackfit/conforming-stacks']
        self._search_original = search.recommend

        def counted(doc):
            self._calls += 1
            return self._route_original(doc)

        http_api.ROUTES['/stackfit/conforming-stacks'] = counted
        search.recommend = counted
        self._server = http_api.server(0)
        self._port = self._server.server_port
        self._thread = Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        self._http = build_opener(ProxyHandler({}))

    def stop(self):
        http_api.ROUTES['/stackfit/conforming-stacks'] = self._route_original
        search.recommend = self._search_original
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=4)

    def _post(self, path, payload):
        body = json.dumps(payload).encode('utf-8')
        req = Request(f'http://127.0.0.1:{self._port}{path}', data=body,
                      headers={'Content-Type': 'application/json'})
        try:
            with self._http.open(req, timeout=5) as response:
                return json.loads(response.read().decode('utf-8'))
        except HTTPError as exc:
            if exc.code == 400:
                raise AdapterRejected(exc.read().decode('utf-8')) from exc
            raise

    def decide(self, previous, request):
        return self._post('/stackfit/reuse-decision',
                          {'previous': previous, 'request': request})

    def full_search(self, request):
        return self._post('/stackfit/conforming-stacks', request)

    def certificate_status(self, request):
        return self._post('/stackfit/certificate-status', request)

    def full_search_calls(self):
        return self._calls

    def reset_counters(self):
        self._calls = 0
