import runpy
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import registry as R

SEED = Path(__file__).resolve().parent.parent / "seed_registry.py"


class SeedRegistryTests(unittest.TestCase):
    def seed(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        db = Path(tmp.name) / "registry.db"
        with patch.object(R, "REGISTRY_DB", db):
            runpy.run_path(str(SEED))
        con = sqlite3.connect(db)
        con.row_factory = sqlite3.Row
        self.addCleanup(con.close)
        return con

    def test_03b_is_seeded_as_the_agentic_drafter(self):
        row = self.seed().execute(
            "SELECT * FROM agents WHERE agent_no = '03b'").fetchone()
        self.assertEqual(row["delivery_box"], "agent")
        self.assertEqual(row["is_agentic"], 1)
        self.assertEqual(row["profile"], "p1-drafting")
        self.assertIn("signed claim set", row["guardrail"])

    def test_reseeding_keeps_03b_agentic(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        db = Path(tmp.name) / "registry.db"
        with patch.object(R, "REGISTRY_DB", db):
            runpy.run_path(str(SEED))
            runpy.run_path(str(SEED))
        con = sqlite3.connect(db)
        self.addCleanup(con.close)
        self.assertEqual(con.execute(
            "SELECT is_agentic, profile FROM agents WHERE agent_no = '03b'"
        ).fetchone(), (1, "p1-drafting"))
