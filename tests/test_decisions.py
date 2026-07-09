import pytest
from tests.conftest import auth_headers


def _create(client):
    resp = client.post(
        "/v1/approval-requests",
        json={"sourceType": "publication", "sourceId": "pub_1", "reviewerUserIds": []},
        headers={**auth_headers(), "Idempotency-Key": "create-1"},
    )
    return resp.json()["id"]


def test_approve_transitions_pending_to_approved(client):
    request_id = _create(client)
    resp = client.post(f"/v1/approval-requests/{request_id}/approve", json={}, headers=auth_headers())
    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"
    assert resp.json()["decidedByUserId"] == "user_alice"


def test_reject_requires_reason(client):
    request_id = _create(client)
    resp = client.post(f"/v1/approval-requests/{request_id}/reject", json={}, headers=auth_headers())
    assert resp.status_code == 422  # reason is a required field


def test_reject_transitions_pending_to_rejected(client):
    request_id = _create(client)
    resp = client.post(
        f"/v1/approval-requests/{request_id}/reject",
        json={"reason": "does not meet brand guidelines"},
        headers=auth_headers(),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"
    assert resp.json()["decisionReason"] == "does not meet brand guidelines"


def test_cancel_transitions_pending_to_cancelled(client):
    request_id = _create(client)
    resp = client.post(f"/v1/approval-requests/{request_id}/cancel", json={}, headers=auth_headers())
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"


def test_cancel_requires_cancel_permission(client):
    request_id = _create(client)
    resp = client.post(
        f"/v1/approval-requests/{request_id}/cancel",
        json={},
        headers=auth_headers(permissions=["approval:read", "approval:decide"]),  # no approval:cancel
    )
    assert resp.status_code == 403


@pytest.mark.parametrize(
    "first_action,second_action,second_payload",
    [
        ("approve", "reject", {"reason": "trying to undo"}),
        ("approve", "cancel", {}),
        ("approve", "approve", {}),
        ("reject", "approve", {}),
        ("cancel", "reject", {"reason": "trying to undo"}),
    ],
)
def test_cannot_transition_out_of_final_state(client, first_action, second_action, second_payload):
    request_id = _create(client)

    first_payload = {"reason": "initial decision"} if first_action == "reject" else {}
    first_resp = client.post(
        f"/v1/approval-requests/{request_id}/{first_action}",
        json=first_payload,
        headers=auth_headers(),
    )
    assert first_resp.status_code == 200

    second_resp = client.post(
        f"/v1/approval-requests/{request_id}/{second_action}",
        json=second_payload,
        headers=auth_headers(),
    )
    assert second_resp.status_code == 409