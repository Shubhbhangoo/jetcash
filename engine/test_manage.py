#!/usr/bin/env python3
import hashlib
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile
import manage
import package_source

class ManagerTests(unittest.TestCase):
    def test_partial_dependencies_trigger_installation(self):
        with patch.object(manage.shutil, "which", return_value="/usr/bin/dpkg-query"):
            with patch.object(manage.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout="installed\n" * len(manage.PACKAGES))):
                self.assertTrue(manage.dependencies())
            with patch.object(manage.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout="installed\n" * (len(manage.PACKAGES) - 1) + "not-installed\n")):
                self.assertFalse(manage.dependencies())

    def test_amounts_are_exact(self):
        self.assertEqual(manage.amount_atomic("0.00000001"), 1)
        self.assertEqual(manage.amount_atomic("1.12345678"), 112345678)
        self.assertEqual(manage.amount_atomic("10000000"), 1000000000000000)
        for value in ("0", "-1", "1e4", "nan", "1.123456789", "10000000.00000001", " 1", "01", "1;echo"):
            with self.subTest(value=value), self.assertRaises(RuntimeError): manage.amount_atomic(value)

    def test_peer_validation(self):
        for value in ("127.0.0.1:41080", "node.example.org:41080", "[::1]:41080"):
            self.assertEqual(manage.peer_address(value), value)
        for value in ("host", "https://host:80/", "user:pass@host:80", "host:0", "host:65536", "host:80/a", "host:80?x", "host:80#x", "-bad.example:80"):
            with self.subTest(value=value), self.assertRaises(RuntimeError): manage.peer_address(value)

    def test_private_state_and_wallet_names(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {"JETCASH_HOME": root}):
            manager = manage.Manager()
            manager.config["peers"] = ["127.0.0.1:41080"]
            manager.save()
            self.assertEqual(manager.config_file.stat().st_mode & 0o777, 0o600)
            self.assertEqual(manager.control.stat().st_mode & 0o777, 0o700)
            self.assertEqual(manage.Manager().config["peers"], ["127.0.0.1:41080"])
            for name in ("../keys", "a/b", "", ".hidden", "x" * 65):
                with self.assertRaises(RuntimeError): manager.name(name)

    def test_different_genesis_is_never_adopted(self):
        with patch.object(manage.Manager, "daemon", side_effect=[{"nettype": "mainnet", "version": "jetcash-test"},
                    {"block_header": {"hash": "00" * 32}}]):
            with self.assertRaisesRegex(RuntimeError, "genesis"): manage.Manager().node_info()

    def test_different_service_is_never_adopted(self):
        with patch.object(manage.Manager, "daemon", return_value={"nettype": "mainnet", "version": "different-software"}):
            with self.assertRaisesRegex(RuntimeError, "different node"): manage.Manager().node_info()

    def test_source_package_excludes_local_state(self):
        with tempfile.TemporaryDirectory() as root:
            archive_path = Path(root) / "source.zip"
            count, digest = package_source.package(archive_path)
            self.assertGreater(count, 20)
            self.assertEqual(digest, hashlib.sha256(archive_path.read_bytes()).hexdigest())
            with zipfile.ZipFile(archive_path) as archive:
                names = archive.namelist()
                for name in names:
                    self.assertNotIn("/dev-data/", name)
                    self.assertNotIn("/artifacts/", name)
                    self.assertNotIn("/.git/", name)
                    self.assertFalse(name.endswith((".keys", ".log", ".wallet")))
                manifest = json.loads(archive.read("jetcash/SOURCE-MANIFEST.json"))
                for name, checksum in manifest.items():
                    self.assertEqual(hashlib.sha256(archive.read("jetcash/" + name)).hexdigest(), checksum)
                self.assertIn("jetcash/LICENSE", names)
                self.assertIn("jetcash/NOTICE", names)

if __name__ == "__main__": unittest.main()
