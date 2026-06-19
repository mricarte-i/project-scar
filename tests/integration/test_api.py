from __future__ import annotations

from tests.conftest import ADMIN_KEY

AUTH = {"X-API-Key": ADMIN_KEY}
SAT_ID = "sat-123"


# auth for admin endpoints


def test_upload_without_api_key_fails(client):
    asset_type = "body_to_payload"
    payload = {
        "quaternion": [
            0.00808936460768732,
            0.00483359305280839,
            0.004488464035575687,
            0.9999455246407403,
        ]
    }
    response = client.post(
        f"/admin/v1/satellites/{SAT_ID}/assets/{asset_type}/versions",
        json={"valid_from": "2025-01-01T00:00:00Z", "payload": payload},
    )
    assert response.status_code == 401


def test_upload_with_bad_api_key_fails(client):
    asset_type = "body_to_payload"
    payload = {
        "quaternion": [
            0.00808936460768732,
            0.00483359305280839,
            0.004488464035575687,
            0.9999455246407403,
        ]
    }
    response = client.post(
        f"/admin/v1/satellites/{SAT_ID}/assets/{asset_type}/versions",
        json={"valid_from": "2025-01-01T00:00:00Z", "payload": payload},
        headers={"X-API-Key": "bad-key"},
    )
    assert response.status_code == 401


# lookups


def test_point_in_time_404_uses_error_out(client):
    response = client.get(f"/v1/satellites/{SAT_ID}/assets/darkframe?at=2025-01-01T00:00:00Z")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "no_asset_valid"
    assert "details" in body["error"]


def test_bulk_returns_all_types_null_when_empty(client):
    response = client.get(
        f"/v1/satellites/{SAT_ID}/assets?at=2025-01-01T00:00:00Z",
    )
    assert response.status_code == 200
    body = response.json()
    assert body["satellite_id"] == SAT_ID
    assert set(body["assets"].keys()) == {
        "darkframe",
        "grayframe",
        "body_to_payload",
        "vicarious_cal_gains",
    }
    assert all(v is None for v in body["assets"].values())


# TODO:
# - query params validation
# - the "upload->resolve->retire" flow
# - frame file upload
