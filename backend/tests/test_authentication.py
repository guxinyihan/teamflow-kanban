"""Authentication boundaries and password compatibility at the HTTP endpoint."""
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt


def test_http_identity_requires_signature_algorithm_and_all_access_claims(client, db):
    from app.auth.utils import create_access_token, get_password_hash
    from app.config import settings
    from app.models import User

    user = User(username="claims", email="claims@example.test",
                hashed_password=get_password_hash("Claims test password 42!"))
    db.add(user)
    db.commit()
    valid = create_access_token({"sub": user.id})
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {valid}"}).status_code == 200

    now = datetime.now(timezone.utc)
    claims = {"sub": str(user.id), "type": "access", "iss": "teamflow", "aud": "teamflow-api",
              "iat": now, "exp": now + timedelta(minutes=5), "jti": "auth-regression"}
    variants = {
        "expired": {**claims, "exp": now - timedelta(seconds=5)},
        "future-issued": {**claims, "iat": now + timedelta(minutes=5)},
        "wrong-issuer": {**claims, "iss": "another-application"},
        "wrong-audience": {**claims, "aud": "another-api"},
        "refresh-type": {**claims, "type": "refresh"},
        "nonnumeric-subject": {**claims, "sub": "someone-else"},
        "unknown-account": {**claims, "sub": str(user.id + 10000)},
    }
    for required in ("sub", "exp", "iat", "type", "jti", "iss", "aud"):
        variants[f"missing-{required}"] = {key: value for key, value in claims.items() if key != required}
    tokens = {name: jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")
              for name, payload in variants.items()}
    tokens["wrong-signature"] = jwt.encode(claims, "different-test-secret-" * 3, algorithm="HS256")
    tokens["wrong-algorithm"] = jwt.encode(claims, settings.JWT_SECRET, algorithm="HS384")
    tokens["unsigned"] = jwt.encode(claims, "", algorithm="none")
    for name, token in tokens.items():
        response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401, name
        assert response.headers["www-authenticate"] == "Bearer", name
        assert "hashed_password" not in response.text, name


def test_legacy_bcrypt_login_preserves_compatibility_then_upgrades_to_argon2(client, db):
    from app.auth.utils import verify_password
    from app.models import User

    # Upstream bcrypt truncated at 72 bytes. Retain that compatibility for the
    # successful legacy login, then bind the upgraded hash to the full password.
    password = "Legacy password 42! " * 5
    legacy_hash = bcrypt.hashpw(password.encode()[:72], bcrypt.gensalt(rounds=4)).decode()
    user = User(username="LegacyUser", email="Legacy@Example.Test", hashed_password=legacy_hash)
    db.add(user)
    db.commit()
    denied = client.post("/api/auth/login", data={"username": "legacyuser", "password": "wrong password"})
    assert denied.status_code == 401
    db.refresh(user)
    assert user.hashed_password == legacy_hash

    accepted = client.post("/api/auth/login", data={"username": "LEGACY@EXAMPLE.TEST", "password": password})
    assert accepted.status_code == 200
    assert "hashed_password" not in accepted.text
    db.refresh(user)
    upgraded = user.hashed_password
    assert upgraded.startswith("$argon2")
    assert verify_password(password, upgraded)
    assert not verify_password(password[:72] + "different suffix", upgraded)
    headers = {"Authorization": f"Bearer {accepted.json()['access_token']}"}
    assert client.get("/api/auth/me", headers=headers).json()["id"] == user.id


def test_new_passwords_preserve_bytes_beyond_legacy_bcrypt_limit(client, db):
    from app.models import User

    password = "A long modern password 42! " * 4
    response = client.post("/api/auth/register", json={
        "username": "modern", "email": "modern@example.test", "password": password,
    })
    assert response.status_code == 201
    assert "hashed_password" not in response.text
    user = db.get(User, response.json()["id"])
    assert user.hashed_password.startswith("$argon2")
    denied = client.post("/api/auth/login", data={"username": "modern", "password": password[:72] + "wrong suffix"})
    assert denied.status_code == 401
    accepted = client.post("/api/auth/login", data={"username": "MODERN", "password": password})
    assert accepted.status_code == 200


def test_unrecognized_or_malformed_password_hashes_fail_without_server_error(client, db):
    from app.models import User

    user = User(username="damaged", email="damaged@example.test", hashed_password="legacy-invalid")
    db.add(user)
    db.commit()
    for stored in ("legacy-invalid", "$2b$malformed", "$argon2id$malformed", ""):
        user.hashed_password = stored
        db.commit()
        response = client.post("/api/auth/login", data={"username": "damaged", "password": "Test password 42!"})
        assert response.status_code == 401
        db.refresh(user)
        assert user.hashed_password == stored
