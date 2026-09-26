from app.models.user import User
from app.routes.data_portability import _serialize_user
from app.services.rate_limiter import limiter

PROFILE_FIELDS = {"id", "email", "full_name", "is_active", "totp_enabled",
                  "last_login_at", "created_at", "updated_at"}


def test_user_serializer_allows_only_profile_fields():
    user = User(id="synthetic", email="synthetic@example.com", full_name="Synthetic",
                password_hash="synthetic-password-hash", totp_secret="JBSWY3DPEHPK3PXP",
                totp_enabled=True, is_superuser=True, token_version=7)
    result = _serialize_user(user)
    assert set(result) <= PROFILE_FIELDS
    assert result["totp_enabled"] is True
    assert result["email"] == user.email
    for field in ("password_hash", "totp_secret", "totp_secret_ciphertext", "token_version", "is_superuser"):
        assert field not in result


def test_organization_export_never_exposes_member_mfa_secret(client, db):
    limiter.clear()
    try:
        registered = client.post("/v1/auth/register", json={
            "email": "export-safety@example.com", "password": "SyntheticExportCheck42!",
            "full_name": "Export Safety", "organization_name": "Isolated Export QA",
        })
        assert registered.status_code == 201
        identity = registered.json()
        user = db.get(User, identity["user_id"])
        user.totp_secret = "JBSWY3DPEHPK3PXP"
        user.totp_enabled = True
        password_hash = user.password_hash
        db.commit()
        response = client.get(f"/v1/organizations/{identity['organization_id']}/export",
                              headers={"Authorization": f"Bearer {identity['access_token']}"})
        assert response.status_code == 200
        assert user.totp_secret not in response.text
        assert password_hash not in response.text
        members = response.json()["members"]
        assert len(members) == 1
        profile = members[0]["user"]
        assert profile["id"] == identity["user_id"]
        assert profile["totp_enabled"] is True
        assert set(profile) <= PROFILE_FIELDS
    finally:
        limiter.clear()
