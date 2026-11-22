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


def initialize(path, product):
    db = connect(path)
    try:
        version = db.execute('PRAGMA user_version').fetchone()[0]
        if version not in (0, 1):
            raise Problem('database_version')
        if version == 0:
            objects = db.execute("SELECT 1 FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").fetchone()
            if objects:
                # Another initializer might have completed between these reads.
                if db.execute('PRAGMA user_version').fetchone()[0] != 1:
                    raise Problem('database_not_empty')
            else:
                sql = Path(__file__).with_name('schema.sql').read_text(encoding='utf-8')
                db.executescript(f'BEGIN IMMEDIATE;\n{sql}\nPRAGMA user_version=1;\nCOMMIT;')
        with transaction(db, write=True):
            db.execute('INSERT OR IGNORE INTO identity VALUES (1, ?)', (product,))
            owner = db.execute('SELECT product FROM identity WHERE singleton=1').fetchone()[0]
            if owner != product:
                raise Problem('database_product')
    finally:
        db.close()
