CREATE TABLE IF NOT EXISTS identity (
    singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
    product TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS drafts (
    id TEXT PRIMARY KEY NOT NULL, dataset TEXT NOT NULL, base INTEGER NOT NULL,
    source TEXT NOT NULL, raw TEXT NOT NULL, raw_sha TEXT NOT NULL,
    document TEXT NOT NULL, document_sha TEXT NOT NULL,
    state TEXT NOT NULL CHECK(state IN ('ready', 'rejected', 'published')),
    reason TEXT, created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS drafts_by_dataset ON drafts(dataset, created, id);
CREATE TABLE IF NOT EXISTS versions (
    id TEXT PRIMARY KEY NOT NULL REFERENCES drafts(id),
    dataset TEXT NOT NULL, document TEXT NOT NULL, document_sha TEXT NOT NULL,
    created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(dataset, id)
);
CREATE TABLE IF NOT EXISTS heads (
    dataset TEXT PRIMARY KEY NOT NULL, generation INTEGER NOT NULL CHECK(generation > 0),
    revision TEXT NOT NULL, FOREIGN KEY(dataset, revision) REFERENCES versions(dataset, id)
);
CREATE TABLE IF NOT EXISTS publication_events (
    dataset TEXT NOT NULL, generation INTEGER NOT NULL, revision TEXT NOT NULL,
    action TEXT NOT NULL CHECK(action IN ('publish', 'restore')),
    created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(dataset, generation),
    FOREIGN KEY(dataset, revision) REFERENCES versions(dataset, id)
);
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY NOT NULL, revision TEXT NOT NULL REFERENCES versions(id),
    operation TEXT NOT NULL, engine TEXT NOT NULL, output TEXT NOT NULL, output_sha TEXT NOT NULL,
    created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(revision, operation, engine)
);
CREATE INDEX IF NOT EXISTS runs_by_revision ON runs(revision, created, id);
