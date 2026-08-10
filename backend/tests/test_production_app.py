from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.production_app import create_production_app


class ProductionAppTest(unittest.TestCase):
    def test_serves_static_frontend_and_preserves_api_routes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            static_root = Path(directory)
            (static_root / "index.html").write_text(
                "<!doctype html><title>GFM release</title>", encoding="utf-8"
            )
            base_app = FastAPI()

            @base_app.get("/api/probe")
            def probe() -> dict[str, bool]:
                return {"ok": True}

            client = TestClient(
                create_production_app(static_root, base_app=base_app)
            )
            self.assertEqual(client.get("/api/probe").json(), {"ok": True})
            self.assertIn("GFM release", client.get("/").text)
            self.assertIn("GFM release", client.get("/client-route").text)
            self.assertEqual(client.get("/missing.js").status_code, 404)

    def test_missing_frontend_fails_fast(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, "frontend is missing"):
                create_production_app(directory, base_app=FastAPI())


if __name__ == "__main__":
    unittest.main()
