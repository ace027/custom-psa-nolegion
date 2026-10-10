import json
from datetime import UTC, datetime

import httpx
import pytest

from app.mail.graph import BusyItem, GraphClient, GraphError, event_payload


def make_client(handler):
    calls = []

    def wrapped(request: httpx.Request):
        calls.append(request)
        if request.url.host == "login.microsoftonline.com":
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        return handler(request)

    http = httpx.Client(transport=httpx.MockTransport(wrapped))
    return GraphClient("tenant", "cid", "secret", "support@msp.com", http=http), calls


def test_create_event_sends_transaction_id_and_returns_id():
    seen = {}

    def handler(request):
        seen["req"] = request
        seen["body"] = json.loads(request.content)
        return httpx.Response(201, json={"id": "EV1"})

    client, _ = make_client(handler)
    assert client.create_event("tech@msp.com", {"subject": "x"}, "txn-1") == "EV1"
    assert seen["req"].method == "POST"
    assert seen["req"].url.path.endswith("/users/tech@msp.com/events")
    assert seen["body"] == {"subject": "x", "transactionId": "txn-1"}


def test_update_event_patches_event_url():
    seen = {}

    def handler(request):
        seen["req"] = request
        return httpx.Response(200, json={})

    client, _ = make_client(handler)
    client.update_event("tech@msp.com", "EV1", {"subject": "y"})
    assert seen["req"].method == "PATCH"
    assert seen["req"].url.path.endswith("/users/tech@msp.com/events/EV1")
    assert json.loads(seen["req"].content) == {"subject": "y"}


def test_delete_event_treats_404_as_success():
    client, _ = make_client(lambda r: httpx.Response(404, json={}))
    client.delete_event("tech@msp.com", "gone")


def test_delete_event_500_is_transient():
    client, _ = make_client(lambda r: httpx.Response(500, text="boom"))
    with pytest.raises(GraphError) as ei:
        client.delete_event("tech@msp.com", "EV1")
    assert ei.value.status == 500 and ei.value.transient is True


@pytest.mark.parametrize("status,transient", [(429, True), (503, True)])
def test_throttle_and_unavailable_are_transient(status, transient):
    client, _ = make_client(lambda r: httpx.Response(status, text="x"))
    with pytest.raises(GraphError) as ei:
        client.update_event("tech@msp.com", "EV1", {})
    assert ei.value.status == status and ei.value.transient is transient


@pytest.mark.parametrize("status", [400, 401, 403])
def test_client_errors_are_permanent(status):
    client, _ = make_client(lambda r: httpx.Response(status, text="no"))
    with pytest.raises(GraphError) as ei:
        client.create_event("tech@msp.com", {}, "t")
    assert ei.value.status == status and ei.value.transient is False


def test_transport_error_is_transient():
    def handler(request):
        raise httpx.ConnectError("down")

    client, _ = make_client(handler)
    with pytest.raises(GraphError) as ei:
        client.create_event("tech@msp.com", {}, "t")
    assert ei.value.status is None and ei.value.transient is True


def test_get_schedule_parses_items_drops_free_and_maps_errors():
    seen = {}

    def handler(request):
        seen["req"] = request
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "value": [
                    {
                        "scheduleId": "Tech@MSP.com",
                        "scheduleItems": [
                            {
                                "status": "busy",
                                "start": {
                                    "dateTime": "2026-10-12T09:00:00.0000000",
                                    "timeZone": "UTC",
                                },
                                "end": {
                                    "dateTime": "2026-10-12T10:00:00.0000000",
                                    "timeZone": "UTC",
                                },
                            },
                            {
                                "status": "free",
                                "start": {"dateTime": "2026-10-12T11:00:00", "timeZone": "UTC"},
                                "end": {"dateTime": "2026-10-12T12:00:00", "timeZone": "UTC"},
                            },
                            {
                                "status": "workingElsewhere",
                                "start": {"dateTime": "2026-10-12T13:00:00Z", "timeZone": "UTC"},
                                "end": {"dateTime": "2026-10-12T14:00:00Z", "timeZone": "UTC"},
                            },
                        ],
                    },
                    {
                        "scheduleId": "Other@msp.com",
                        "error": {"message": "no permission", "responseCode": "ErrorAccessDenied"},
                    },
                ]
            },
        )

    client, _ = make_client(handler)
    start = datetime(2026, 10, 12, 0, 0, tzinfo=UTC)
    end = datetime(2026, 10, 13, 0, 0, tzinfo=UTC)
    out = client.get_schedule("support@msp.com", ["Tech@MSP.com", "Other@msp.com"], start, end)

    assert seen["req"].url.path.endswith("/users/support@msp.com/calendar/getSchedule")
    assert seen["req"].headers["Prefer"] == 'outlook.timezone="UTC"'
    assert seen["body"]["startTime"] == {"dateTime": "2026-10-12T00:00:00", "timeZone": "UTC"}
    assert seen["body"]["availabilityViewInterval"] == 15
    assert set(out) == {"tech@msp.com", "other@msp.com"}
    assert out["other@msp.com"] == []
    assert out["tech@msp.com"] == [
        BusyItem(
            datetime(2026, 10, 12, 9, tzinfo=UTC), datetime(2026, 10, 12, 10, tzinfo=UTC), "busy"
        ),
        BusyItem(
            datetime(2026, 10, 12, 13, tzinfo=UTC),
            datetime(2026, 10, 12, 14, tzinfo=UTC),
            "workingElsewhere",
        ),
    ]


def test_event_payload_has_only_the_approved_fields():
    p = event_payload(
        42,
        datetime(2026, 10, 12, 9, 0, tzinfo=UTC),
        datetime(2026, 10, 12, 10, 0, tzinfo=UTC),
        "https://psa.example.com/",
    )
    assert set(p) == {
        "subject",
        "body",
        "start",
        "end",
        "sensitivity",
        "showAs",
        "isReminderOn",
    }
    assert p["subject"] == "PSA #42 appointment"
    assert p["body"] == {"contentType": "text", "content": "https://psa.example.com/tickets/42"}
    assert p["start"] == {"dateTime": "2026-10-12T09:00:00", "timeZone": "UTC"}
    assert p["sensitivity"] == "private" and p["showAs"] == "busy" and p["isReminderOn"] is False
