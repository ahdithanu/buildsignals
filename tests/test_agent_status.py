"""Offline harness checks without importing the application or its environment."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "agent_status.py"
SPEC = importlib.util.spec_from_file_location("agent_status", SCRIPT)
agent_status = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(agent_status)

PROFILE = "docs/forgeos-project-profile.md"
WORKFLOW = "docs/forgeos-delivery-loop.md"
MANIFEST = ".forgeos/adoption.json"
ADAPTERS = ("CLAUDE.md", "GEMINI.md", ".github/copilot-instructions.md")
SOURCES = (
    "docs/governence/engineering_constitution.md",
    "docs/governence/engineering_workflow.md",
    "docs/ai/ai_engineering_principles.md",
    "docs/projects/multi_agent_protocol.md",
)


class AgentStatusTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "project"
        self.forgeos = Path(self.temp.name) / "forgeos"
        for name in (
            "AGENTS.md", *ADAPTERS, "docs/agent-handoff.md", "docs/agent-onboarding.md",
            "docs/templates/agent-handoff.md", PROFILE, WORKFLOW,
        ):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("AGENTS.md docs/agent-handoff.md\n", encoding="utf-8")
        (self.root / "AGENTS.md").write_text(f"{PROFILE}\n{WORKFLOW}\n", encoding="utf-8")
        self.manifest = {
            "schema_version": 1,
            "project": "BuildSignals",
            "profile": PROFILE,
            "workflow": WORKFLOW,
            "source_root_hint": "../ForgeOS",
            "reviewed_on": "2026-11-20",
            "sources": [
                {"path": name, "sha256": hashlib.sha256(name.encode()).hexdigest()}
                for name in SOURCES
            ],
        }
        self.write_manifest()

    def write_manifest(self):
        path = self.root / MANIFEST
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.manifest), encoding="utf-8")

    def write_sources(self):
        for name in SOURCES:
            path = self.forgeos / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(name.encode())

    def run_status(self, *args):
        output = io.StringIO()
        with (
            patch.object(agent_status, "ROOT", self.root),
            patch.object(agent_status, "git", return_value="offline"),
            patch.object(agent_status.shutil, "which", return_value=None),
            patch.object(sys, "argv", [str(SCRIPT), *args]),
            redirect_stdout(output),
        ):
            code = agent_status.main()
        return code, output.getvalue()

    def test_default_check_does_not_read_source_bytes_or_need_forgeos(self):
        with patch.object(Path, "read_bytes", side_effect=AssertionError("external read")):
            code, output = self.run_status("--check")
        self.assertEqual(code, 0, output)
        self.assertFalse(self.forgeos.exists())

    def test_check_requires_forgeos_files(self):
        for name in (PROFILE, WORKFLOW, MANIFEST):
            with self.subTest(name=name):
                path = self.root / name
                original = path.read_bytes()
                path.unlink()
                code, output = self.run_status("--check")
                path.write_bytes(original)
                self.assertEqual(code, 1, output)
                self.assertIn(name, output)

    def test_agents_links_forgeos_docs_without_requiring_adapter_links(self):
        for missing in (PROFILE, WORKFLOW):
            with self.subTest(missing=missing):
                (self.root / "AGENTS.md").write_text(
                    WORKFLOW if missing == PROFILE else PROFILE, encoding="utf-8",
                )
                code, output = self.run_status("--check")
                self.assertEqual(code, 1, output)
                self.assertIn(missing, output)

    def test_adapters_still_require_shared_references(self):
        for name in ADAPTERS:
            for content in ("AGENTS.md", "docs/agent-handoff.md"):
                with self.subTest(name=name, content=content):
                    path = self.root / name
                    path.write_text(content, encoding="utf-8")
                    code, output = self.run_status("--check")
                    path.write_text("AGENTS.md docs/agent-handoff.md", encoding="utf-8")
                    self.assertEqual(code, 1, output)
                    self.assertIn(f"{name}: missing shared", output)

    def test_check_rejects_invalid_json_or_encoding(self):
        for content in (b"{", b"\xff"):
            with self.subTest(content=content):
                (self.root / MANIFEST).write_bytes(content)
                code, output = self.run_status("--check")
                self.assertEqual(code, 1, output)
                self.assertIn(MANIFEST, output)

    def test_check_rejects_nonobject_manifest(self):
        for manifest in (None, [], 1, "manifest"):
            with self.subTest(manifest=manifest):
                self.manifest = manifest
                self.write_manifest()
                code, output = self.run_status("--check")
                self.assertEqual(code, 1, output)
                self.assertIn(MANIFEST, output)

    def test_check_rejects_wrong_contract_fields(self):
        for key, values in (
            ("schema_version", (None, True, 1.0, "1", 2)),
            ("project", (None, "Other")),
            ("profile", (None, "docs/other.md")),
            ("workflow", (None, "docs/other.md")),
            ("sources", (None, [], {}, "sources")),
        ):
            original = self.manifest[key]
            for value in values:
                with self.subTest(key=key, value=value):
                    self.manifest[key] = value
                    self.write_manifest()
                    code, output = self.run_status("--check")
                    self.assertEqual(code, 1, output)
                    self.assertIn(key, output)
            self.manifest[key] = original

    def test_check_rejects_malformed_source_entries(self):
        for source in (None, [], "source", {}, {"path": SOURCES[0]}, {"sha256": "a" * 64}):
            with self.subTest(source=source):
                self.manifest["sources"] = [source]
                self.write_manifest()
                code, output = self.run_status("--check")
                self.assertEqual(code, 1, output)
                self.assertIn("sources", output)

    def test_check_rejects_unsafe_source_paths_before_reading(self):
        for name in (
            None, 1, "", ".", "..", "../outside.md", "/absolute.md",
            "docs/../outside.md", "./docs/file.md", "docs//file.md", "docs/file.md/",
            "docs\\file.md", "C:/outside.md", "C:\\outside.md", "//host/share.md",
            "docs/\x00file.md", "docs/\nfile.md",
        ):
            with self.subTest(name=name):
                self.manifest["sources"] = [{"path": name, "sha256": "a" * 64}]
                self.write_manifest()
                with patch.object(Path, "read_bytes", side_effect=AssertionError("unsafe read")):
                    code, output = self.run_status("--check")
                self.assertEqual(code, 1, output)
                self.assertIn("path", output)

    def test_check_requires_lowercase_sha256(self):
        for digest in (None, 1, "", "a" * 63, "a" * 65, "A" * 64, "g" * 64, "a" * 64 + "\n"):
            with self.subTest(digest=digest):
                self.manifest["sources"] = [{"path": SOURCES[0], "sha256": digest}]
                self.write_manifest()
                code, output = self.run_status("--check")
                self.assertEqual(code, 1, output)
                self.assertIn("sha256", output)

    def test_explicit_root_verifies_all_source_bytes(self):
        self.write_sources()
        code, output = self.run_status("--check", "--forgeos-root", str(self.forgeos))
        self.assertEqual(code, 0, output)
        for name in SOURCES:
            self.assertIn(name, output)

    def test_explicit_root_fails_when_missing_even_without_check(self):
        code, output = self.run_status("--forgeos-root", str(self.forgeos))
        self.assertEqual(code, 1, output)
        self.assertIn("ForgeOS", output)

    def test_explicit_root_rejects_missing_and_drifted_sources(self):
        self.write_sources()
        (self.forgeos / SOURCES[-1]).unlink()
        (self.forgeos / SOURCES[0]).write_bytes(b"changed\r\n")
        code, output = self.run_status("--check", "--forgeos-root", str(self.forgeos))
        self.assertEqual(code, 1, output)
        self.assertIn(SOURCES[-1], output)
        self.assertIn(SOURCES[0], output)
        self.assertIn("sha256", output)

    def test_explicit_root_rejects_symlink_escape(self):
        self.write_sources()
        outside = Path(self.temp.name) / "outside.md"
        outside.write_bytes(SOURCES[0].encode())
        path = self.forgeos / SOURCES[0]
        path.unlink()
        path.symlink_to(outside)
        code, output = self.run_status("--check", "--forgeos-root", str(self.forgeos))
        self.assertEqual(code, 1, output)
        self.assertIn(SOURCES[0], output)

    def test_status_remains_informational_without_check(self):
        (self.root / MANIFEST).unlink()
        code, output = self.run_status()
        self.assertEqual(code, 0, output)
        self.assertIn(f"MISSING {MANIFEST}", output)


if __name__ == "__main__":
    unittest.main()
