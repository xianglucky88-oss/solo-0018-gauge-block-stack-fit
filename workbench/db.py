from contextlib import contextmanager
from pathlib import Path
import sqlite3

from .errors import Problem


def connect(path):
    db = sqlite3.connect(path, timeout=3, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    return db


@contextmanager
def transaction(db, *, write=False):
    db.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
    try:
        yield
        db.commit()
    except BaseException:
        db.rollback()
        raise


def _apply_schema(db, filename):
    statements = Path(__file__).with_name(filename).read_text(encoding='utf-8')
    pending = ''
    for line in statements.splitlines(keepends=True):
        pending += line
        if sqlite3.complete_statement(pending):
            db.execute(pending)
            pending = ''
    if pending.strip():
        raise ValueError(f'incomplete SQL in {filename}')


def initialize(path, product):
    db = connect(path)
    try:
        with transaction(db, write=True):
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0, 1, 2):
                raise Problem('database_version')
            if version == 0:
                if db.execute("SELECT 1 FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").fetchone():
                    raise Problem('database_not_empty')
                _apply_schema(db, 'schema.sql')
            db.execute('INSERT OR IGNORE INTO identity VALUES (1, ?)', (product,))
            owner = db.execute('SELECT product FROM identity WHERE singleton=1').fetchone()[0]
            if owner != product:
                raise Problem('database_product')
            if version < 2:
                _apply_schema(db, 'handoff.sql')
                db.execute('PRAGMA user_version=2')
    finally:
        db.close()
