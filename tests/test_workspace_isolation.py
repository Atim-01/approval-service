from tests.conftest import auth_headers


def _create(client, workspace_id="ws_1"):
    resp = client.post(
        "/v1/approval-requests",
        json={"sourceType": "publication", "sourceId": "pub_1", "reviewerUserIds": []},
        headers={**auth_headers(workspace_id=workspace_id), "Idempotency-Key": "create-1"},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def test_cannot_read_request_from_another_workspace(client):
    request_id = _create(client, workspace_id="ws_1")

    resp = client.get(
        f"/v1/approval-requests/{request_id}",
        headers=auth_headers(workspace_id="ws_2"),
    )
    assert resp.status_code == 404


def test_cannot_approve_request_from_another_workspace(client):
    request_id = _create(client, workspace_id="ws_1")

    resp = client.post(
        f"/v1/approval-requests/{request_id}/approve",
        json={},
        headers=auth_headers(workspace_id="ws_2"),
    )
    assert resp.status_code == 404


def test_cannot_cancel_request_from_another_workspace(client):
    request_id = _create(client, workspace_id="ws_1")

    resp = client.post(
        f"/v1/approval-requests/{request_id}/cancel",
        json={},
        headers=auth_headers(workspace_id="ws_2"),
    )
    assert resp.status_code == 404


def test_same_id_visible_only_in_owning_workspace(client):
    request_id = _create(client, workspace_id="ws_1")

    ok_resp = client.get(
        f"/v1/approval-requests/{request_id}",
        headers=auth_headers(workspace_id="ws_1"),
    )
    assert ok_resp.status_code == 200
    assert ok_resp.json()["id"] == request_id