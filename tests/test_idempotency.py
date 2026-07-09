from tests.conftest import auth_headers


def test_repeated_create_with_same_key_returns_same_id(client):
    payload = {"sourceType": "publication", "sourceId": "pub_1", "reviewerUserIds": []}
    headers = {**auth_headers(), "Idempotency-Key": "dup-key"}

    resp1 = client.post("/v1/approval-requests", json=payload, headers=headers)
    resp2 = client.post("/v1/approval-requests", json=payload, headers=headers)

    assert resp1.status_code == 201
    assert resp2.status_code == 201
    assert resp1.json()["id"] == resp2.json()["id"]

    list_resp = client.get("/v1/approval-requests", headers=auth_headers())
    assert list_resp.json()["total"] == 1  # no duplicate was created


def test_same_key_different_body_is_rejected(client):
    headers = {**auth_headers(), "Idempotency-Key": "reused-key"}

    resp1 = client.post(
        "/v1/approval-requests",
        json={"sourceType": "publication", "sourceId": "pub_1", "reviewerUserIds": []},
        headers=headers,
    )
    assert resp1.status_code == 201

    resp2 = client.post(
        "/v1/approval-requests",
        json={"sourceType": "publication", "sourceId": "pub_DIFFERENT", "reviewerUserIds": []},
        headers=headers,
    )
    assert resp2.status_code == 409


def test_repeated_approve_with_same_key_is_idempotent(client):
    create_resp = client.post(
        "/v1/approval-requests",
        json={"sourceType": "publication", "sourceId": "pub_1", "reviewerUserIds": []},
        headers={**auth_headers(), "Idempotency-Key": "create-for-approve-test"},
    )
    request_id = create_resp.json()["id"]

    headers = {**auth_headers(), "Idempotency-Key": "approve-key-1"}
    resp1 = client.post(f"/v1/approval-requests/{request_id}/approve", json={}, headers=headers)
    resp2 = client.post(f"/v1/approval-requests/{request_id}/approve", json={}, headers=headers)

    assert resp1.status_code == 200
    assert resp2.status_code == 200
    assert resp1.json()["status"] == "approved"
    assert resp2.json()["status"] == "approved"
    assert resp1.json()["decidedAt"] == resp2.json()["decidedAt"]  # same cached response, not re-decided