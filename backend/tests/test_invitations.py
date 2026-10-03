"""Invitation capabilities are expiring, account bound and single use."""

from datetime import datetime, timedelta, timezone

import sqlalchemy as sa


def invite(client, users, board, email="outsider@example.test", role="member", actor="owner"):
    response = client.post(
        f"/api/teams/{board['team_id']}/invitations", headers=users[actor]["headers"],
        json={"email": email, "role": role},
    )
    assert response.status_code in (200, 201), response.text
    return response.json()


def accept(client, users, token, actor="outsider"):
    return client.post("/api/invitations/accept", headers=users[actor]["headers"], json={"token": token})


def test_valid_invite_joins_exact_team_with_bound_role(client, users, board, db):
    invitation = invite(client, users, board)
    assert invitation["token"]
    assert invitation["token"] in invitation["invitation_url"]
    result = accept(client, users, invitation["token"])
    assert result.status_code in (200, 201), result.text
    from app.models import TeamMember
    membership = db.get(TeamMember, (board["team_id"], users["outsider"]["user"]["id"]))
    assert membership is not None
    assert membership.role == "member"


def test_raw_invitation_token_is_not_stored(client, users, board, db):
    invitation = invite(client, users, board)
    table = sa.Table("invitations", sa.MetaData(), autoload_with=db.bind)
    row = db.execute(sa.select(table).where(table.c.id == invitation["id"])).mappings().one()
    assert row["token_hash"] != invitation["token"]
    assert invitation["token"] not in list(row.values())
    listing = client.get(f"/api/teams/{board['team_id']}/invitations", headers=users["owner"]["headers"])
    assert listing.status_code == 200
    assert invitation["token"] not in listing.text
    assert "token_hash" not in listing.text


def test_wrong_account_cannot_consume_invite(client, users, board):
    invitation = invite(client, users, board)
    assert accept(client, users, invitation["token"], actor="member").status_code in (400, 403)
    assert accept(client, users, invitation["token"]).status_code in (200, 201)


def test_invite_replay_rejected(client, users, board):
    invitation = invite(client, users, board)
    assert accept(client, users, invitation["token"]).status_code in (200, 201)
    assert accept(client, users, invitation["token"]).status_code in (400, 409, 410)


def test_revoked_invite_cannot_join(client, users, board):
    invitation = invite(client, users, board)
    response = client.delete(f"/api/invitations/{invitation['id']}", headers=users["owner"]["headers"])
    assert response.status_code in (200, 204)
    assert accept(client, users, invitation["token"]).status_code in (400, 409, 410)


def test_expired_invite_cannot_join(client, users, board, db):
    invitation = invite(client, users, board)
    table = sa.Table("invitations", sa.MetaData(), autoload_with=db.bind)
    db.execute(sa.update(table).where(table.c.id == invitation["id"]).values(
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    ))
    db.commit()
    assert accept(client, users, invitation["token"]).status_code in (400, 409, 410)


def test_member_and_outsider_cannot_issue_invites(client, users, board):
    for actor in ("member", "outsider"):
        response = client.post(f"/api/teams/{board['team_id']}/invitations", headers=users[actor]["headers"],
                               json={"email": "new@example.test", "role": "member"})
        assert response.status_code in (403, 404)


def test_admin_cannot_invite_another_admin(client, users, board):
    response = client.post(f"/api/teams/{board['team_id']}/invitations", headers=users["admin"]["headers"],
                           json={"email": "outsider@example.test", "role": "admin"})
    assert response.status_code in (403, 422)


def test_already_member_and_owner_invites_rejected(client, users, board):
    for email, role in (("member@example.test", "member"), ("outsider@example.test", "owner")):
        response = client.post(f"/api/teams/{board['team_id']}/invitations", headers=users["owner"]["headers"],
                               json={"email": email, "role": role})
        assert response.status_code in (400, 409, 422)


def test_non_admin_cannot_revoke_an_invite(client, users, board):
    invitation = invite(client, users, board)
    response = client.delete(f"/api/invitations/{invitation['id']}", headers=users["member"]["headers"])
    assert response.status_code in (403, 404)
    assert accept(client, users, invitation["token"]).status_code in (200, 201)
