CREATE TABLE auctions (
    id uuid PRIMARY KEY,
    title text NOT NULL,
    starting_price_cents bigint NOT NULL,
    current_price_cents bigint,
    minimum_increment_cents bigint NOT NULL,
    winning_bid_id uuid,
    version bigint NOT NULL DEFAULT 0,
    starts_at timestamptz NOT NULL,
    ends_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),

    CONSTRAINT auctions_title_length
        CHECK (char_length(btrim(title)) BETWEEN 1 AND 200),
    CONSTRAINT auctions_starting_price_positive
        CHECK (starting_price_cents BETWEEN 1 AND 9000000000000000),
    CONSTRAINT auctions_current_price_range
        CHECK (
            current_price_cents IS NULL
            OR current_price_cents BETWEEN starting_price_cents AND 9000000000000000
        ),
    CONSTRAINT auctions_increment_positive
        CHECK (minimum_increment_cents BETWEEN 1 AND 9000000000000000),
    CONSTRAINT auctions_time_order CHECK (ends_at > starts_at),
    CONSTRAINT auctions_version_nonnegative CHECK (version >= 0),
    CONSTRAINT auctions_bid_state_consistent CHECK (
        (
            current_price_cents IS NULL
            AND winning_bid_id IS NULL
            AND version = 0
        )
        OR
        (
            current_price_cents IS NOT NULL
            AND winning_bid_id IS NOT NULL
            AND version > 0
        )
    )
);

CREATE TABLE bids (
    id uuid PRIMARY KEY,
    request_id uuid NOT NULL,
    auction_id uuid NOT NULL,
    bidder_id text NOT NULL,
    amount_cents bigint NOT NULL,
    auction_version bigint NOT NULL,
    accepted_at timestamptz NOT NULL DEFAULT clock_timestamp(),

    CONSTRAINT bids_request_id_unique UNIQUE (request_id),
    CONSTRAINT bids_auction_and_id_unique UNIQUE (auction_id, id),
    CONSTRAINT bids_auction_fk
        FOREIGN KEY (auction_id) REFERENCES auctions(id) ON DELETE CASCADE,
    CONSTRAINT bids_bidder_id_length
        CHECK (char_length(btrim(bidder_id)) BETWEEN 1 AND 128),
    CONSTRAINT bids_amount_range
        CHECK (amount_cents BETWEEN 1 AND 9000000000000000),
    CONSTRAINT bids_version_positive CHECK (auction_version > 0)
);

ALTER TABLE auctions
    ADD CONSTRAINT auctions_winning_bid_fk
    FOREIGN KEY (id, winning_bid_id)
    REFERENCES bids (auction_id, id)
    DEFERRABLE INITIALLY DEFERRED;

CREATE INDEX bids_auction_history_idx
    ON bids (auction_id, auction_version DESC, accepted_at DESC);

CREATE INDEX auctions_open_window_idx
    ON auctions (starts_at, ends_at);

