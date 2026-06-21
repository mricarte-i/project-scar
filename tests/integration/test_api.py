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


# query params validation


def test_invalid_timestamp_fails_lookup(client):
    response = client.get(f"/v1/satellites/{SAT_ID}/assets/darkframe?at=invalid-timestamp")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


# - the "upload->resolve->retire" flow


def test_upload_then_resolve(client, fake_blobstore):
    upload_response = client.post(
        f"/admin/v1/satellites/{SAT_ID}/assets/vicarious_cal_gains/versions",
        json={"valid_from": "2025-01-01T00:00:00Z", "payload": {"gain": 4.27}},
        headers=AUTH,
    )
    assert upload_response.status_code == 201, upload_response.text
    created = upload_response.json()["created"]
    assert created["asset_type"] == "vicarious_cal_gains"

    assert len(fake_blobstore.objects) == 1

    got_response = client.get(
        f"/v1/satellites/{SAT_ID}/assets/vicarious_cal_gains?at=2025-06-01T00:00:00Z",
    )
    assert got_response.status_code == 200, got_response.text
    body = got_response.json()
    assert body["version_id"] == created["version_id"]
    assert body["payload"]["media_type"] == "application/json"
    assert body["payload"]["url"].startswith("https://blobstore.test/")


def test_supersede_then_retire_flow(client):
    base = f"/admin/v1/satellites/{SAT_ID}/assets/body_to_payload/versions"
    client.post(
        base,
        json={"valid_from": "2020-01-01T00:00:00Z", "payload": {"v": 1}},
        headers=AUTH,
    )
    supersede_response = client.post(
        base,
        json={
            "valid_from": "2025-01-01T00:00:00Z",
            "payload": {"v": 2},
        },
        headers=AUTH,
    )
    assert supersede_response.status_code == 201
    assert supersede_response.json()["superseded"], (
        "expected the prior version version to be reported as superseded"
    )

    retire_response = client.post(
        f"/admin/v1/satellites/{SAT_ID}/assets/body_to_payload/versions/retire",
        json={"effective_from": "2025-06-01T00:00:00Z"},
        headers=AUTH,
    )
    assert retire_response.status_code == 200

    gap = client.get(
        f"/v1/satellites/{SAT_ID}/assets/body_to_payload?at=2025-07-01T00:00:00Z",
    )
    assert gap.status_code == 404, "after the retire instant there is a deliberate gap"
    # TODO:
    # - frame file upload
