"""Verify that insert_custom_kg data appears in /graph/entities/all.

This script tests the critical assumption that insert_custom_kg writes to
BOTH the graph layer and the document layer.

Usage:
    .venv/bin/python scripts/verify_insert_custom_kg.py
"""

import asyncio
import json
import sys
import time

import httpx

BASE_URL = "http://internal.example.invalid:3001"
WORKSPACE = "test-insert-kg-verify"
HEADERS = {
    "LIGHTRAG-WORKSPACE": WORKSPACE,
    "Content-Type": "application/json",
}


async def main() -> None:
    async with httpx.AsyncClient(
        base_url=BASE_URL, timeout=30.0, trust_env=False
    ) as client:
        # Step 1: Clear workspace
        print(f"[1/5] Clearing workspace '{WORKSPACE}'...")
        resp = await client.delete("/graph/clear", headers=HEADERS)
        print(f"  Clear: {resp.status_code} — {resp.json()}")
        await asyncio.sleep(3)  # Wait for async cleanup

        # Step 2: Verify empty
        print("[2/5] Verifying workspace is empty...")
        resp = await client.get("/graph/entities/all", headers=HEADERS)
        entities_before = resp.json()
        print(f"  Entities before: {len(entities_before)}")
        assert len(entities_before) == 0, f"Expected 0, got {len(entities_before)}"

        # Step 3: Insert via insert_custom_kg
        print("[3/5] Inserting test data via /documents/insert_custom_kg...")
        payload = {
            "custom_kg": {
                "chunks": [
                    {
                        "content": "class AuthService:\n    def login(self, user, password):\n        return validate(user, password)",
                        "source_id": "src/auth/service.py",
                        "tokens": 30,
                        "chunk_order_index": 0,
                        "full_doc_id": "src/auth/service.py",
                    }
                ],
                "entities": [
                    {
                        "entity_name": "AuthService",
                        "entity_type": "class",
                        "description": "Authentication service handling user login",
                        "source_id": "src/auth/service.py",
                    },
                    {
                        "entity_name": "AuthService.login",
                        "entity_type": "method",
                        "description": "Login method that validates user credentials",
                        "source_id": "src/auth/service.py",
                    },
                    {
                        "entity_name": "validate",
                        "entity_type": "function",
                        "description": "Validates user credentials",
                        "source_id": "src/auth/validators.py",
                    },
                ],
                "relationships": [
                    {
                        "src_id": "AuthService.login",
                        "tgt_id": "validate",
                        "description": "login calls validate for credential checking",
                        "keywords": "CALLS",
                        "weight": 1.0,
                        "source_id": "src/auth/service.py",
                    },
                    {
                        "src_id": "AuthService",
                        "tgt_id": "AuthService.login",
                        "description": "AuthService defines login method",
                        "keywords": "DEFINES",
                        "weight": 1.0,
                        "source_id": "src/auth/service.py",
                    },
                ],
            }
        }

        start = time.time()
        resp = await client.post(
            "/documents/insert_custom_kg", headers=HEADERS, json=payload
        )
        duration = time.time() - start
        print(f"  insert_custom_kg: {resp.status_code} ({duration:.2f}s)")
        print(f"  Response: {json.dumps(resp.json(), indent=2)}")

        if resp.status_code != 200:
            print("  FAILED: insert_custom_kg returned non-200")
            sys.exit(1)

        # Step 4: Query graph layer
        print("[4/5] Querying /graph/entities/all (graph layer)...")
        await asyncio.sleep(2)  # Give time for persistence

        resp = await client.get("/graph/entities/all", headers=HEADERS)
        entities_after = resp.json()
        print(f"  Entities after: {len(entities_after)}")

        if len(entities_after) > 0:
            print("  GRAPH LAYER: DATA FOUND")
            for e in entities_after:
                name = e.get("entity_name", e.get("id", "?"))
                etype = e.get("entity_type", "?")
                print(f"    - {name} ({etype})")
        else:
            print("  GRAPH LAYER: NO DATA (insert_custom_kg did NOT write to graph layer)")

        resp = await client.get("/graph/relations/all", headers=HEADERS)
        relations_after = resp.json()
        print(f"  Relations after: {len(relations_after)}")

        if len(relations_after) > 0:
            print("  GRAPH RELATIONS: DATA FOUND")
            for r in relations_after:
                src = r.get("src_id", r.get("source", "?"))
                tgt = r.get("tgt_id", r.get("target", "?"))
                kw = r.get("keywords", "?")
                print(f"    - {src} --[{kw}]--> {tgt}")
        else:
            print("  GRAPH RELATIONS: NO DATA")

        # Step 5: Test RAG query (document layer)
        print("[5/5] Testing /query (document layer RAG)...")
        try:
            resp = await client.post(
                "/query",
                headers=HEADERS,
                json={"query": "What does AuthService do?", "mode": "local"},
            )
            if resp.status_code == 200:
                answer = resp.json()
                if isinstance(answer, dict):
                    text = answer.get("response", str(answer))[:200]
                else:
                    text = str(answer)[:200]
                print(f"  RAG response: {text}")
            else:
                print(f"  RAG query: {resp.status_code} — {resp.text[:200]}")
        except Exception as e:
            print(f"  RAG query failed: {e}")

        # Summary
        print("\n" + "=" * 60)
        print("VERIFICATION SUMMARY")
        print("=" * 60)
        graph_ok = len(entities_after) >= 3
        relations_ok = len(relations_after) >= 2
        print(f"  Graph entities:  {'PASS' if graph_ok else 'FAIL'} ({len(entities_after)}/3 expected)")
        print(f"  Graph relations: {'PASS' if relations_ok else 'FAIL'} ({len(relations_after)}/2 expected)")
        print(f"  Injection time:  {duration:.2f}s (vs ~350s for graph CRUD)")

        if graph_ok and relations_ok:
            print("\n  CONCLUSION: insert_custom_kg DOES write to graph layer.")
            print("  LoomGraph can switch from N×entity/create to 1×insert_custom_kg.")
        else:
            print("\n  CONCLUSION: insert_custom_kg does NOT write to graph layer.")
            print("  LoomGraph must continue using graph CRUD endpoints.")

        # Cleanup
        await client.delete("/graph/clear", headers=HEADERS)
        print(f"\n  Cleaned up workspace '{WORKSPACE}'.")


if __name__ == "__main__":
    asyncio.run(main())
