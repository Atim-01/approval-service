from tests.conftest import auth_headers


def _create_payload(**overrides):
    payload = {
        "sourceType": "publication",
        "sourceId": "pub_123",
        "reviewerUserIds": ["user_bob"],
        "title": "New homepage banner",
        "description": "Please review before it goes live",
    }
    payload.update(overrides)
    return payload


def test_create_approval_request_success(client):
    resp = client.post(
        "/v1/approval-requests",
        json=_create_payload(),
        headers={**auth_headers(), "Idempotency-Key": "key-1"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "pending"
    assert body["sourceType"] == "publication"
    assert body["sourceId"] == "pub_123"
    assert body["requestedByUserId"] == "user_alice"
    assert body["reviewerUserIds"] == ["user_bob"]


def test_create_requires_idempotency_key(client):
    resp = client.post(
        "/v1/approval-requests",
        json=_create_payload(),
        headers=auth_headers(),  # no Idempotency-Key
    )
    assert resp.status_code == 400


def test_create_requires_permission(client):
    resp = client.post(
        "/v1/approval-requests",
        json=_create_payload(),
        headers={
            **auth_headers(permissions=["approval:read"]),  # no approval:create
            "Idempotency-Key": "key-2",
        },
    )
    assert resp.status_code == 403


def test_get_request_returns_created_request(client):
    create_resp = client.post(
        "/v1/approval-requests",
        json=_create_payload(),
        headers={**auth_headers(), "Idempotency-Key": "key-3"},
    )
    request_id = create_resp.json()["id"]

    get_resp = client.get(f"/v1/approval-requests/{request_id}", headers=auth_headers())
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == request_id


def test_get_nonexistent_request_returns_404(client):
    resp = client.get("/v1/approval-requests/does-not-exist", headers=auth_headers())
    assert resp.status_code == 404


def test_list_requests_scoped_to_workspace(client):
    client.post(
        "/v1/approval-requests",
        json=_create_payload(sourceId="pub_1"),
        headers={**auth_headers(workspace_id="ws_1"), "Idempotency-Key": "key-a"},
    )
    client.post(
        "/v1/approval-requests",
        json=_create_payload(sourceId="pub_2"),
        headers={**auth_headers(workspace_id="ws_2"), "Idempotency-Key": "key-b"},
    )

    resp_ws1 = client.get("/v1/approval-requests", headers=auth_headers(workspace_id="ws_1"))
    assert resp_ws1.status_code == 200
    body_ws1 = resp_ws1.json()
    assert body_ws1["total"] == 1
    assert body_ws1["items"][0]["sourceId"] == "pub_1"

    resp_ws2 = client.get("/v1/approval-requests", headers=auth_headers(workspace_id="ws_2"))
    body_ws2 = resp_ws2.json()
    assert body_ws2["total"] == 1
    assert body_ws2["items"][0]["sourceId"] == "pub_2"