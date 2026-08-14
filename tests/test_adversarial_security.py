"""Adversarial stress testing suite for Security, RBAC, and Authentication boundaries.

Challenger 1 (Milestone M2) - Empirical verification of:
1. Token tampering, expired tokens, forged roles, invalid signatures, algorithm confusion.
2. Cross-user document deletion attempts via API.
3. Cross-user document listing leaks and unauthorized discovery.
4. Cross-user retrieval and BM25 sparse search context isolation.
5. Bootstrap admin registration hijacking attempts and case-variation bypasses.
"""

from __future__ import annotations

import io
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from jose import jwt

from app.core.config import Settings, get_settings
from app.core.security import UserStore
from app.main import app
from app.services.ingestion import DocumentRegistry
from app.services.rag_service import RAGService


@pytest.fixture(autouse=True)
def _reset_global_state():
    """Reset UserStore and DocumentRegistry state before and after each test."""
    UserStore.users = {}
    DocumentRegistry._records = {}
    yield
    UserStore.users = {}
    DocumentRegistry._records = {}


@pytest.fixture()
def adversarial_env(tmp_path):
    """Setup an isolated environment with authentication and bootstrap admin configured."""
    secret = "adversarial-super-secret-key-32-bytes!!"
    settings = Settings(
        auth_secret=secret,
        auth_bootstrap_admin="admin",
        auth_bootstrap_password="SuperAdminPassword123!",
        upload_dir=tmp_path / "uploads",
        chroma_path=tmp_path / "chroma",
        bm25_index_path=tmp_path / "chroma" / "bm25_index.json",
        openai_api_key="test-key",
    )
    app.dependency_overrides[get_settings] = lambda: settings
    client = TestClient(app)
    yield client, settings
    app.dependency_overrides.pop(get_settings, None)


# ===========================================================================
# 1. TOKEN TAMPERING & CRYPTOGRAPHIC ADVERSARIAL TESTS
# ===========================================================================

class TestTokenTamperingAndCryptoBoundaries:
    """Adversarially probe JWT parsing, signature verification, and role handling."""

    def test_jwt_none_algorithm_rejected(self, adversarial_env):
        """Attacker attempts JWT algorithm confusion using 'none' algorithm."""
        client, settings = adversarial_env
        UserStore.add("victim", "Password123!", "user")

        import base64
        import json
        header = base64.urlsafe_b64encode(json.dumps({"alg": "none", "typ": "JWT"}).encode()).decode().rstrip("=")
        payload = base64.urlsafe_b64encode(
            json.dumps({"sub": "victim", "role": "admin", "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp())}).encode()
        ).decode().rstrip("=")
        token_none = f"{header}.{payload}."

        resp = client.get("/documents", headers={"Authorization": f"Bearer {token_none}"})
        assert resp.status_code == 401
        assert "Invalid or expired token" in resp.json().get("detail", "")

    def test_jwt_wrong_secret_signature_rejected(self, adversarial_env):
        """Attacker signs a valid payload using their own secret key."""
        client, settings = adversarial_env
        UserStore.add("alice", "Password123!", "user")

        attacker_secret = "attacker-unauthorized-secret-key-12345"
        forged_token = jwt.encode(
            {"sub": "alice", "role": "admin", "exp": datetime.now(UTC) + timedelta(hours=1)},
            key=attacker_secret,
            algorithm="HS256",
        )

        resp = client.get("/documents", headers={"Authorization": f"Bearer {forged_token}"})
        assert resp.status_code == 401
        assert "Invalid or expired token" in resp.json().get("detail", "")

    def test_jwt_expired_token_rejected(self, adversarial_env):
        """Attacker reuses an expired token."""
        client, settings = adversarial_env
        UserStore.add("bob", "Password123!", "user")

        expired_time = datetime.now(UTC) - timedelta(minutes=10)
        expired_token = jwt.encode(
            {"sub": "bob", "role": "user", "exp": expired_time},
            key=settings.auth_secret,
            algorithm="HS256",
        )

        resp = client.get("/documents", headers={"Authorization": f"Bearer {expired_token}"})
        assert resp.status_code == 401
        assert "Invalid or expired token" in resp.json().get("detail", "")

    def test_jwt_tampered_payload_rejected(self, adversarial_env):
        """Attacker alters payload in transit without knowing the secret."""
        client, settings = adversarial_env
        UserStore.add("charlie", "Password123!", "user")

        valid_token = jwt.encode(
            {"sub": "charlie", "role": "user", "exp": datetime.now(UTC) + timedelta(hours=1)},
            key=settings.auth_secret,
            algorithm="HS256",
        )

        parts = valid_token.split(".")
        # Tamper payload part (middle base64 segment)
        tampered_token = f"{parts[0]}.eyJzdWIiOiJhZG1pbiIsInJvbGUiOiJhZG1pbiJ9.{parts[2]}"

        resp = client.get("/documents", headers={"Authorization": f"Bearer {tampered_token}"})
        assert resp.status_code == 401

    def test_jwt_tampered_signature_byte_flip(self, adversarial_env):
        """Single character corruption in signature must trigger 401."""
        client, settings = adversarial_env
        UserStore.add("dan", "Password123!", "user")

        valid_token = jwt.encode(
            {"sub": "dan", "role": "user", "exp": datetime.now(UTC) + timedelta(hours=1)},
            key=settings.auth_secret,
            algorithm="HS256",
        )
        corrupted_token = valid_token[:-2] + ("X" if valid_token[-1] != "X" else "Y")

        resp = client.get("/documents", headers={"Authorization": f"Bearer {corrupted_token}"})
        assert resp.status_code == 401

    def test_jwt_forged_role_cannot_elevate_privileges(self, adversarial_env):
        """Attacker has legitimate account 'eve' (role=user).

        Even if a token is crafted with role='admin', the server resolves the user
        from UserStore and enforces the actual database role.
        """
        client, settings = adversarial_env
        UserStore.add("eve", "Password123!", "user")

        # Forge token claiming role=admin signed with correct secret
        forged_admin_token = jwt.encode(
            {"sub": "eve", "role": "admin", "exp": datetime.now(UTC) + timedelta(hours=1)},
            key=settings.auth_secret,
            algorithm="HS256",
        )

        # Upload a document owned by another user "victim"
        UserStore.add("victim", "Password123!", "user")
        victim_token = jwt.encode(
            {"sub": "victim", "role": "user", "exp": datetime.now(UTC) + timedelta(hours=1)},
            key=settings.auth_secret,
            algorithm="HS256",
        )
        upload_resp = client.post(
            "/documents/upload",
            files={"file": ("victim_doc.txt", io.BytesIO(b"Victim Private Sensitive Data"), "text/plain")},
            headers={"Authorization": f"Bearer {victim_token}"},
        )
        assert upload_resp.status_code == 201
        doc_id = upload_resp.json()["document_id"]

        # Eve attempts to delete victim's document using forged admin token
        delete_resp = client.delete(
            f"/documents/{doc_id}",
            headers={"Authorization": f"Bearer {forged_admin_token}"},
        )
        # Must be rejected because UserStore evaluates eve's real role as "user"
        assert delete_resp.status_code == 403
        assert "do not have permission" in delete_resp.json().get("detail", "")

    def test_jwt_unknown_or_ghost_sub_rejected(self, adversarial_env):
        """Token with subject not present in UserStore must be rejected."""
        client, settings = adversarial_env
        ghost_token = jwt.encode(
            {"sub": "ghost_user_does_not_exist", "role": "user", "exp": datetime.now(UTC) + timedelta(hours=1)},
            key=settings.auth_secret,
            algorithm="HS256",
        )

        resp = client.get("/documents", headers={"Authorization": f"Bearer {ghost_token}"})
        assert resp.status_code == 401
        assert "User not found" in resp.json().get("detail", "")

    def test_malformed_auth_headers(self, adversarial_env):
        """Malformed authorization headers must return 401 on protected endpoints."""
        client, _ = adversarial_env
        bad_headers = [
            "Bearer ",
            "Bearer",
            "Bearer not-a-jwt",
            "Bearer eyJhbGciOi.incomplete",
            "Basic dXNlcjpwYXNz",
            "Token 12345",
        ]
        for header in bad_headers:
            resp = client.delete(f"/documents/{uuid4()}", headers={"Authorization": header})
            assert resp.status_code == 401, f"Failed for header: {header}"


# ===========================================================================
# 2. BOOTSTRAP ADMIN REGISTRATION HIJACKING TESTS
# ===========================================================================

class TestBootstrapAdminHijackPrevention:
    """Adversarially probe bootstrap administrator registration defense."""

    def test_register_bootstrap_admin_exact_match_blocked(self, adversarial_env):
        """Direct registration of bootstrap admin username returns HTTP 400."""
        client, settings = adversarial_env
        resp = client.post(
            "/auth/register",
            json={"username": settings.auth_bootstrap_admin, "password": "AttackerPass123!"},
        )
        assert resp.status_code == 400
        assert "reserved for system administration" in resp.json().get("detail", "")

    @pytest.mark.parametrize("spoofed_username", ["ADMIN", "Admin", "aDmIn", "  admin  ", "\tadmin\n"])
    def test_register_bootstrap_admin_case_and_whitespace_spoofs_blocked(self, adversarial_env, spoofed_username):
        """Case variations and whitespace padding around admin username must be blocked."""
        client, _ = adversarial_env
        resp = client.post(
            "/auth/register",
            json={"username": spoofed_username, "password": "AttackerPass123!"},
        )
        assert resp.status_code in (400, 422)

    def test_bootstrap_admin_login_lifecycle(self, adversarial_env):
        """Bootstrap admin logs in, is created with role='admin', and can perform admin ops."""
        client, settings = adversarial_env

        # 1. Login with correct bootstrap credentials
        resp = client.post(
            "/auth/login",
            json={"username": settings.auth_bootstrap_admin, "password": settings.auth_bootstrap_password},
        )
        assert resp.status_code == 200
        admin_token = resp.json()["access_token"]

        # Verify admin user in store has role='admin'
        admin_record = UserStore.get(settings.auth_bootstrap_admin)
        assert admin_record is not None
        assert admin_record["role"] == "admin"

        # 2. Login with wrong bootstrap password fails
        bad_resp = client.post(
            "/auth/login",
            json={"username": settings.auth_bootstrap_admin, "password": "WrongPassword!"},
        )
        assert bad_resp.status_code == 401

    def test_registration_ignores_injected_role_field(self, adversarial_env):
        """Attacker sends role='admin' in registration payload body."""
        client, _ = adversarial_env
        resp = client.post(
            "/auth/register",
            json={"username": "sneaky_user", "password": "Password123!", "role": "admin"},
        )
        assert resp.status_code == 201

        user_record = UserStore.get("sneaky_user")
        assert user_record is not None
        assert user_record["role"] == "user", "Role must remain 'user' despite injection attempt"


# ===========================================================================
# 3. CROSS-USER DOCUMENT DELETION ADVERSARIAL TESTS
# ===========================================================================

class TestCrossUserDocumentDeletion:
    """Adversarially probe document deletion access controls."""

    def test_unauthenticated_deletion_rejected_when_auth_enabled(self, adversarial_env):
        """Unauthenticated delete attempts must fail with 401."""
        client, settings = adversarial_env

        # Alice creates a document
        UserStore.add("alice", "Pass123!", "user")
        alice_token = jwt.encode(
            {"sub": "alice", "role": "user", "exp": datetime.now(UTC) + timedelta(hours=1)},
            key=settings.auth_secret,
            algorithm="HS256",
        )
        upload_resp = client.post(
            "/documents/upload",
            files={"file": ("alice_secret.txt", io.BytesIO(b"Alice confidential plans"), "text/plain")},
            headers={"Authorization": f"Bearer {alice_token}"},
        )
        doc_id = upload_resp.json()["document_id"]

        # Anonymous caller attempts deletion
        anon_resp = client.delete(f"/documents/{doc_id}")
        assert anon_resp.status_code == 401
        assert "Authentication is required" in anon_resp.json().get("detail", "")

        # Document must still exist
        assert DocumentRegistry.get(doc_id) is not None

    def test_cross_user_deletion_rejected_with_403(self, adversarial_env):
        """User Bob cannot delete Alice's document."""
        client, settings = adversarial_env

        # Alice creates doc
        UserStore.add("alice", "Pass123!", "user")
        alice_token = jwt.encode(
            {"sub": "alice", "role": "user", "exp": datetime.now(UTC) + timedelta(hours=1)},
            key=settings.auth_secret,
            algorithm="HS256",
        )
        upload_resp = client.post(
            "/documents/upload",
            files={"file": ("alice_vault.txt", io.BytesIO(b"Alice Secret Vault Content"), "text/plain")},
            headers={"Authorization": f"Bearer {alice_token}"},
        )
        doc_id = upload_resp.json()["document_id"]

        # Bob attempts deletion
        UserStore.add("bob", "Pass123!", "user")
        bob_token = jwt.encode(
            {"sub": "bob", "role": "user", "exp": datetime.now(UTC) + timedelta(hours=1)},
            key=settings.auth_secret,
            algorithm="HS256",
        )
        bob_resp = client.delete(
            f"/documents/{doc_id}",
            headers={"Authorization": f"Bearer {bob_token}"},
        )
        assert bob_resp.status_code == 403
        assert "do not have permission" in bob_resp.json().get("detail", "")

        # Document must still exist in registry
        assert DocumentRegistry.get(doc_id) is not None

    def test_owner_can_delete_own_document(self, adversarial_env):
        """Alice can successfully delete her own document."""
        client, settings = adversarial_env

        UserStore.add("alice", "Pass123!", "user")
        alice_token = jwt.encode(
            {"sub": "alice", "role": "user", "exp": datetime.now(UTC) + timedelta(hours=1)},
            key=settings.auth_secret,
            algorithm="HS256",
        )
        upload_resp = client.post(
            "/documents/upload",
            files={"file": ("alice_temp.txt", io.BytesIO(b"Alice Temporary Document"), "text/plain")},
            headers={"Authorization": f"Bearer {alice_token}"},
        )
        doc_id = upload_resp.json()["document_id"]

        del_resp = client.delete(
            f"/documents/{doc_id}",
            headers={"Authorization": f"Bearer {alice_token}"},
        )
        assert del_resp.status_code == 204
        assert DocumentRegistry.get(doc_id) is None

    def test_admin_can_delete_any_user_document(self, adversarial_env):
        """Admin can delete any user's document."""
        client, settings = adversarial_env

        UserStore.add("alice", "Pass123!", "user")
        alice_token = jwt.encode(
            {"sub": "alice", "role": "user", "exp": datetime.now(UTC) + timedelta(hours=1)},
            key=settings.auth_secret,
            algorithm="HS256",
        )
        upload_resp = client.post(
            "/documents/upload",
            files={"file": ("alice_report.txt", io.BytesIO(b"Alice Quarterly Report"), "text/plain")},
            headers={"Authorization": f"Bearer {alice_token}"},
        )
        doc_id = upload_resp.json()["document_id"]

        # Admin logs in and deletes Alice's document
        login_resp = client.post(
            "/auth/login",
            json={"username": settings.auth_bootstrap_admin, "password": settings.auth_bootstrap_password},
        )
        admin_token = login_resp.json()["access_token"]

        del_resp = client.delete(
            f"/documents/{doc_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert del_resp.status_code == 204
        assert DocumentRegistry.get(doc_id) is None


# ===========================================================================
# 4. CROSS-USER DOCUMENT LISTING & RETRIEVAL LEAK TESTS
# ===========================================================================

class TestCrossUserListingAndRetrievalIsolation:
    """Adversarially probe document visibility and retrieval leakage."""

    def test_cross_user_listing_isolation_and_no_leakage(self, adversarial_env):
        """Verify strict tenant isolation across anonymous, regular users, and admin."""
        client, settings = adversarial_env

        # 1. Ingest Alice's private document
        UserStore.add("alice", "Pass123!", "user")
        alice_token = jwt.encode(
            {"sub": "alice", "role": "user", "exp": datetime.now(UTC) + timedelta(hours=1)},
            key=settings.auth_secret,
            algorithm="HS256",
        )
        r_alice = client.post(
            "/documents/upload",
            files={"file": ("alice_doc.txt", io.BytesIO(b"Alice Private Blueprint"), "text/plain")},
            headers={"Authorization": f"Bearer {alice_token}"},
        )
        alice_doc_id = r_alice.json()["document_id"]

        # 2. Ingest Bob's private document
        UserStore.add("bob", "Pass123!", "user")
        bob_token = jwt.encode(
            {"sub": "bob", "role": "user", "exp": datetime.now(UTC) + timedelta(hours=1)},
            key=settings.auth_secret,
            algorithm="HS256",
        )
        r_bob = client.post(
            "/documents/upload",
            files={"file": ("bob_doc.txt", io.BytesIO(b"Bob Private Financials"), "text/plain")},
            headers={"Authorization": f"Bearer {bob_token}"},
        )
        bob_doc_id = r_bob.json()["document_id"]

        # 3. Unauthenticated caller list check -> MUST NOT see Alice or Bob docs
        anon_list = client.get("/documents").json()
        anon_ids = {d["document_id"] for d in anon_list["documents"]}
        assert alice_doc_id not in anon_ids
        assert bob_doc_id not in anon_ids
        assert anon_list["total"] == 0

        # 4. Alice list check -> Sees Alice doc, MUST NOT see Bob doc
        alice_list = client.get("/documents", headers={"Authorization": f"Bearer {alice_token}"}).json()
        alice_ids = {d["document_id"] for d in alice_list["documents"]}
        assert alice_doc_id in alice_ids
        assert bob_doc_id not in alice_ids
        assert alice_list["total"] == 1

        # 5. Bob list check -> Sees Bob doc, MUST NOT see Alice doc
        bob_list = client.get("/documents", headers={"Authorization": f"Bearer {bob_token}"}).json()
        bob_ids = {d["document_id"] for d in bob_list["documents"]}
        assert bob_doc_id in bob_ids
        assert alice_doc_id not in bob_ids
        assert bob_list["total"] == 1

        # 6. Admin list check -> Sees both Alice and Bob docs
        admin_login = client.post(
            "/auth/login",
            json={"username": settings.auth_bootstrap_admin, "password": settings.auth_bootstrap_password},
        ).json()
        admin_token = admin_login["access_token"]
        admin_list = client.get("/documents", headers={"Authorization": f"Bearer {admin_token}"}).json()
        admin_ids = {d["document_id"] for d in admin_list["documents"]}
        assert alice_doc_id in admin_ids
        assert bob_doc_id in admin_ids
        assert admin_list["total"] == 2

    def test_retrieval_rbac_isolation_in_rag_service(self, adversarial_env):
        """Adversarially probe RAGService._retrieve for cross-user data leakage."""
        client, settings = adversarial_env
        rag = RAGService(settings)

        # Alice uploads a document with distinct secret terms
        UserStore.add("alice", "Pass123!", "user")
        alice_token = jwt.encode(
            {"sub": "alice", "role": "user", "exp": datetime.now(UTC) + timedelta(hours=1)},
            key=settings.auth_secret,
            algorithm="HS256",
        )
        client.post(
            "/documents/upload",
            files={"file": ("quantum_secret.txt", io.BytesIO(b"QuantumSuperconductorAlgorithmAlphaX99 is top secret."), "text/plain")},
            headers={"Authorization": f"Bearer {alice_token}"},
        )

        # 1. Unauthenticated retrieval for Alice's secret term -> MUST return empty
        anon_chunks = rag._retrieve("QuantumSuperconductorAlgorithmAlphaX99", user=None, hybrid_search=False)
        assert len(anon_chunks) == 0

        # 2. Bob retrieval for Alice's secret term -> MUST return empty
        UserStore.add("bob", "Pass123!", "user")
        bob_user = UserStore.get("bob")
        bob_chunks = rag._retrieve("QuantumSuperconductorAlgorithmAlphaX99", user=bob_user, hybrid_search=False)
        assert len(bob_chunks) == 0

        # 3. Alice retrieval for her own secret term -> MUST return the chunk
        alice_user = UserStore.get("alice")
        alice_chunks = rag._retrieve("QuantumSuperconductorAlgorithmAlphaX99", user=alice_user, hybrid_search=False)
        assert len(alice_chunks) > 0
        assert "QuantumSuperconductorAlgorithmAlphaX99" in alice_chunks[0].document.page_content

        # 4. Admin retrieval -> MUST return the chunk
        admin_user = {"username": "admin", "role": "admin"}
        admin_chunks = rag._retrieve("QuantumSuperconductorAlgorithmAlphaX99", user=admin_user, hybrid_search=False)
        assert len(admin_chunks) > 0
