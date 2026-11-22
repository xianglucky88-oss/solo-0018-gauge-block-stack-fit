from contextlib import closing

from . import catalog, comparison, dispatch, evidence, history, intake, publication, review, runs
from .codec import identifier
from .db import connect, transaction
from .errors import Problem
from .operations import Operations


class Service:
    def __init__(self, path, profile):
        self.path = path
        self.review_policy = profile.REVIEW
        self.ops = Operations(profile)
        self.writes = {
            '/api/review/open': lambda db, d: review.open_case(db, self.review_policy, d['run'], d['generation']),
            '/api/review/decide': lambda db, d: review.decide(db, d['review'], d['decision']),
            '/api/dispatch': lambda db, d: dispatch.issue(db, d['review']),
            '/api/stage': lambda db, d: intake.stage(db, self.ops, d['dataset'], d['source'], d['text']),
            '/api/publish': lambda db, d: publication.publish(db, d['draft']),
            '/api/restore': lambda db, d: publication.restore(db, d['dataset'], d['revision'], d['generation']),
            '/api/run': lambda db, d: runs.batch(db, self.ops, d['dataset'], d.get('revision'), d['operations']),
        }
        self.reads = {
            '/api/review/history': lambda db, d: {'cases': review.for_run(db, d['run'])},
            '/api/history': lambda db, d: history.for_dataset(db, d['dataset']),
            '/api/compare': lambda db, d: comparison.compare(db, self.ops, d['dataset'], d['before'], d['after'], d['operation']),
            '/api/replay': lambda db, d: runs.replay(db, self.ops, d['run']),
        }

    def post(self, path, data):
        write = path in self.writes
        handler = (self.writes if write else self.reads).get(path)
        if handler is None:
            raise Problem('unknown_endpoint', 404)
        try:
            with closing(connect(self.path)) as db, transaction(db, write=write):
                return handler(db, data)
        except KeyError as exc:
            raise Problem('required_field') from exc

    def get(self, path):
        if path == '/api/meta':
            return self.ops.metadata(), None
        if path == '/api/datasets':
            with closing(connect(self.path)) as db:
                return catalog.listing(db), None
        if path.startswith('/api/dispatch/'):
            case = identifier(path.removeprefix('/api/dispatch/'))
            with closing(connect(self.path)) as db, transaction(db):
                return dispatch.download(db, case), f'delivery-{case[:12]}.json'
        if path.startswith('/api/evidence/'):
            run = identifier(path.removeprefix('/api/evidence/'))
            with closing(connect(self.path)) as db, transaction(db):
                return evidence.export(db, run), f'evidence-{run[:12]}.json'
        raise Problem('unknown_endpoint', 404)
