from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from bidding.api.app import create_app
from bidding.config import Settings
from bidding.db.strategies import StrategyBusyError

pytestmark = pytest.mark.integration


@pytest.fixture
def client(db_pool, clean_database):
    settings = Settings(
        database_url="postgresql://unused/external-pool",
        bid_strategy="pessimistic",
    )
    with TestClient(create_app(settings=settings, pool=db_pool)) as test_client:
        yield test_client


def auction_payload(*, starts_at=None, ends_at=None):
    now = datetime.now(UTC)
    return {
        "title": "Vintage mechanical keyboard",
        "starting_price_cents": 10_000,
        "minimum_increment_cents": 1_500,
        "starts_at": (starts_at or now - timedelta(minutes=1)).isoformat(),
        "ends_at": (ends_at or now + timedelta(hours=1)).isoformat(),
    }


def create_auction(client: TestClient, **overrides):
    payload = auction_payload()
    payload.update(overrides)
    response = client.post("/auctions", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_health_create_and_get_auction(client: TestClient) -> None:
    assert client.get("/health").json() == {
        "status": "ok",
        "bid_strategy": "pessimistic",
    }

    created = create_auction(client)
    fetched = client.get(f"/auctions/{created['id']}")

    assert fetched.status_code == 200
    assert fetched.json() == created
    assert created["current_price_cents"] is None
    assert created["version"] == 0


def test_request_validation_rejects_boolean_money(client: TestClient) -> None:
    payload = auction_payload()
    payload["starting_price_cents"] = True

    response = client.post("/auctions", json=payload)

    assert response.status_code == 422


def test_bid_rejection_returns_reason_and_current_minimum(client: TestClient) -> None:
    auction = create_auction(client)

    response = client.post(
        f"/auctions/{auction['id']}/bids",
        json={
            "request_id": str(uuid4()),
            "bidder_id": "alice",
            "amount_cents": 9_999,
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == {
        "reason": "bid_too_low",
        "minimum_acceptable_cents": 10_000,
    }


def test_accepted_bid_can_be_replayed_and_listed(client: TestClient) -> None:
    auction = create_auction(client)
    request_id = str(uuid4())
    payload = {
        "request_id": request_id,
        "bidder_id": "alice",
        "amount_cents": 10_000,
    }

    accepted = client.post(f"/auctions/{auction['id']}/bids", json=payload)
    replayed = client.post(f"/auctions/{auction['id']}/bids", json=payload)
    history = client.get(f"/auctions/{auction['id']}/bids")

    assert accepted.status_code == 200
    assert accepted.json()["status"] == "accepted"
    assert replayed.status_code == 200
    assert replayed.json()["status"] == "replayed"
    assert replayed.json()["bid"] == accepted.json()["bid"]
    assert history.status_code == 200
    assert len(history.json()) == 1


def test_websocket_gets_snapshot_then_post_commit_event(client: TestClient) -> None:
    auction = create_auction(client)

    with client.websocket_connect(f"/ws/auctions/{auction['id']}") as websocket:
        snapshot = websocket.receive_json()
        response = client.post(
            f"/auctions/{auction['id']}/bids",
            json={
                "request_id": str(uuid4()),
                "bidder_id": "alice",
                "amount_cents": 10_000,
            },
        )
        event = websocket.receive_json()

    assert snapshot["type"] == "auction.snapshot"
    assert snapshot["auction"]["version"] == 0
    assert response.status_code == 200
    assert event["type"] == "auction.bid_accepted"
    assert event["version"] == 1
    assert event["bid"]["id"] == response.json()["bid"]["id"]


def test_rejected_bid_does_not_create_websocket_event(client: TestClient) -> None:
    auction = create_auction(client)

    with client.websocket_connect(f"/ws/auctions/{auction['id']}") as websocket:
        websocket.receive_json()
        rejected = client.post(
            f"/auctions/{auction['id']}/bids",
            json={
                "request_id": str(uuid4()),
                "bidder_id": "alice",
                "amount_cents": 9_999,
            },
        )
        accepted = client.post(
            f"/auctions/{auction['id']}/bids",
            json={
                "request_id": str(uuid4()),
                "bidder_id": "bob",
                "amount_cents": 10_000,
            },
        )
        next_event = websocket.receive_json()

    assert rejected.status_code == 409
    assert accepted.status_code == 200
    assert next_event["type"] == "auction.bid_accepted"
    assert next_event["bid"]["bidder_id"] == "bob"


@pytest.mark.parametrize("strategy", ["unsafe", "pessimistic", "optimistic"])
def test_every_strategy_is_available_through_same_http_contract(
    db_pool, clean_database, strategy
) -> None:
    settings = Settings(
        database_url="postgresql://unused/external-pool",
        bid_strategy=strategy,
    )
    with TestClient(create_app(settings=settings, pool=db_pool)) as strategy_client:
        auction = create_auction(strategy_client)
        response = strategy_client.post(
            f"/auctions/{auction['id']}/bids",
            json={
                "request_id": str(uuid4()),
                "bidder_id": "alice",
                "amount_cents": 10_000,
            },
        )

    assert response.status_code == 200
    assert response.json()["status"] == "accepted"


def test_missing_resources_return_not_found(client: TestClient) -> None:
    missing = uuid4()

    assert client.get(f"/auctions/{missing}").status_code == 404
    assert client.get(f"/auctions/{missing}/bids").status_code == 404
    bid = client.post(
        f"/auctions/{missing}/bids",
        json={
            "request_id": str(uuid4()),
            "bidder_id": "alice",
            "amount_cents": 10_000,
        },
    )
    assert bid.status_code == 404
    assert bid.json()["detail"]["reason"] == "auction_not_found"


def test_database_busy_error_is_mapped_to_retryable_http_response(
    client: TestClient,
) -> None:
    class BusyService:
        def place_bid(self, command):
            raise StrategyBusyError("injected timeout")

    client.app.state.bidding_service = BusyService()
    response = client.post(
        f"/auctions/{uuid4()}/bids",
        json={
            "request_id": str(uuid4()),
            "bidder_id": "alice",
            "amount_cents": 10_000,
        },
    )

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "1"
    assert response.json()["detail"]["reason"] == "database_busy"
