CREATE TABLE reviews (
    id TEXT PRIMARY KEY NOT NULL,
    dataset TEXT NOT NULL,
    generation INTEGER NOT NULL,
    run TEXT NOT NULL REFERENCES runs(id),
    eligible INTEGER NOT NULL CHECK(eligible IN (0, 1)),
    state TEXT NOT NULL DEFAULT 'open' CHECK(state IN ('open', 'approved', 'returned')),
    FOREIGN KEY(dataset, generation) REFERENCES publication_events(dataset, generation),
    UNIQUE(run, generation)
);
CREATE TABLE dispatches (
    review TEXT PRIMARY KEY NOT NULL REFERENCES reviews(id),
    payload_sha TEXT NOT NULL,
    issued TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
