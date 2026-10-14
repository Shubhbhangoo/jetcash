#!/usr/bin/env python3
import sys
import unittest
from unittest.mock import patch
import cli

class CapturedExec(Exception):
    def __init__(self, argv): self.argv = argv

class LauncherTests(unittest.TestCase):
    def argv(self, *arguments):
        def capture(binary, argv): raise CapturedExec(argv)
        with patch.object(sys, "argv", ["jetcash", *arguments]), patch.object(cli.os, "execv", side_effect=capture), patch.object(cli.Path, "is_file", return_value=True):
            with self.assertRaises(CapturedExec) as result: cli.main()
            return result.exception.argv

    def test_mainnet_node_defaults(self):
        argv = self.argv("node")
        self.assertNotIn("--testnet", argv)
        self.assertEqual(argv[argv.index("--p2p-bind-ip") + 1], "0.0.0.0")
        self.assertEqual(argv[argv.index("--rpc-bind-ip") + 1], "127.0.0.1")
        self.assertEqual(argv[argv.index("--zmq-rpc-bind-ip") + 1], "127.0.0.1")

    def test_mainnet_wallet_defaults(self):
        argv = self.argv("wallet", "--mainnet")
        self.assertNotIn("--mainnet", argv)
        self.assertEqual(argv[argv.index("--daemon-address") + 1], "127.0.0.1:41081")

    def test_other_profiles(self):
        for profile, port in [("testnet", 42081), ("stagenet", 43081), ("regtest", 41081)]:
            argv = self.argv("wallet", "--" + profile)
            self.assertEqual(argv[argv.index("--daemon-address") + 1], "127.0.0.1:" + str(port))
            if profile == "regtest": self.assertNotIn("--regtest", argv)

    def test_regression_persistence(self):
        argv = self.argv("node", "--regtest")
        self.assertIn("--keep-fakechain", argv)
        self.assertEqual(argv[argv.index("--p2p-bind-ip") + 1], "127.0.0.1")

    def test_explicit_overrides(self):
        argv = self.argv("wallet", "--daemon-address=example.invalid:10000")
        self.assertNotIn("--daemon-address", argv)
        self.assertIn("--daemon-address=example.invalid:10000", argv)

    def test_conflicts_rejected(self):
        for args in [["--mainnet", "--testnet"], ["--testnet=true"], ["--regtest", "--stagenet"]]:
            with self.assertRaises(RuntimeError): cli.network_arguments(args)

if __name__ == "__main__": unittest.main()
