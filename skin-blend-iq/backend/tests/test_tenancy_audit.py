"""Tenant isolation and immutable audit chain (spec sections 15, 18, 20)."""

from .conftest import create_client_and_case, register_studio


class TestTenantIsolation:
    def test_cross_tenant_access_denied(self, client):
        studio_a = register_studio(client)
        studio_b = register_studio(client)
        bundle = create_client_and_case(client, studio_a["headers"])

        # Studio B cannot read A's client, case, or list them.
        r = client.get(f"/v1/clients/{bundle['client']['id']}", headers=studio_b["headers"])
        assert r.status_code == 404
        r = client.get(f"/v1/cases/{bundle['case']['id']}", headers=studio_b["headers"])
        assert r.status_code == 404
        r = client.get("/v1/clients", headers=studio_b["headers"])
        assert all(c["id"] != bundle["client"]["id"] for c in r.json())

        # Studio B cannot write into A's records.
        r = client.post("/v1/cases", headers=studio_b["headers"], json={
            "client_id": bundle["client"]["id"], "case_type": "burn_scar",
        })
        assert r.status_code == 404

    def test_audit_log_scoped_to_tenant(self, client):
        studio_a = register_studio(client)
        studio_b = register_studio(client)
        create_client_and_case(client, studio_a["headers"])
        r = client.get("/v1/audit-events", headers=studio_b["headers"])
        assert all(e["tenant_id"] == studio_b["tenant"]["id"] for e in r.json())

    def test_unauthenticated_requests_rejected(self, client):
        assert client.get("/v1/clients").status_code == 401
        assert client.get("/v1/dashboard").status_code == 401
        assert client.get("/v1/clients", headers={"Authorization": "Bearer bogus"}).status_code == 401


class TestAuditChain:
    def test_actions_produce_chained_events(self, client):
        studio = register_studio(client)
        create_client_and_case(client, studio["headers"])
        r = client.get("/v1/audit-events", headers=studio["headers"])
        events = r.json()
        actions = {e["action"] for e in events}
        assert "client.created" in actions
        assert "consent.recorded" in actions
        assert "case.created" in actions

        r = client.get("/v1/audit-events/verify", headers=studio["headers"])
        assert r.status_code == 200
        out = r.json()
        assert out["valid"] is True
        assert out["count"] == len(events)

    def test_tampering_detected(self, client):
        studio = register_studio(client)
        create_client_and_case(client, studio["headers"])

        # Tamper directly in the database, then verify must fail.
        from app.db import SessionLocal
        from app.models import AuditEvent

        with SessionLocal() as db:
            ev = (
                db.query(AuditEvent)
                .filter(AuditEvent.tenant_id == studio["tenant"]["id"], AuditEvent.seq == 2)
                .one()
            )
            ev.action = "client.deleted"  # falsify history
            db.add(ev)
            db.commit()

        r = client.get("/v1/audit-events/verify", headers=studio["headers"])
        out = r.json()
        assert out["valid"] is False
        assert out["broken_at_seq"] == 2
