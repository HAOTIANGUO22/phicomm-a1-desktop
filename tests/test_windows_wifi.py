# SPDX-License-Identifier: GPL-3.0-only
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
import uuid

TOOLS = Path(__file__).resolve().parents[1] / 'tools'


def load_tool(name):
    spec = importlib.util.spec_from_file_location(name, TOOLS / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


easylink = load_tool('a1_easylink')
saved = load_tool('send_saved_wifi')


class WindowsWifiTests(unittest.TestCase):
    def test_adapter_is_selected_by_ip_without_assuming_wlan_name(self):
        identifier = '01234567-89ab-cdef-0123-456789abcdef'
        with patch.object(saved.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, identifier + '\n', '')) as run:
            self.assertEqual(saved.adapter_guid('192.0.2.20'), uuid.UUID(identifier))
            command = run.call_args.args[0][-1]
            self.assertIn("Get-NetIPAddress -IPAddress '192.0.2.20'", command)
            self.assertNotIn('-Name WLAN', command)

    def test_optional_adapter_name_is_a_literal_and_still_matches_ip(self):
        identifier = '01234567-89ab-cdef-0123-456789abcdef'
        with patch.object(saved.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, identifier, '')) as run:
            saved.adapter_guid('192.0.2.20', "Wi-Fi' test")
            command = run.call_args.args[0][-1]
            self.assertIn("Get-NetIPAddress -IPAddress '192.0.2.20'", command)
            self.assertIn("$_.Name -eq 'Wi-Fi'' test'", command)

    def test_ambiguous_or_missing_adapter_is_rejected(self):
        for output in ('', 'one\ntwo\n'):
            with patch.object(saved.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, output, '')):
                with self.assertRaises(RuntimeError):
                    saved.adapter_guid('192.0.2.20')

    def test_protected_profile_is_not_mistaken_for_a_plaintext_password(self):
        profile = '''<WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">
          <SSIDConfig><SSID><name>Example24G</name></SSID></SSIDConfig>
          <MSM><security><sharedKey><protected>{}</protected>
          <keyMaterial>test-only-password</keyMaterial></sharedKey></security></MSM>
          </WLANProfile>'''
        self.assertEqual(saved.profile_credentials(profile.format('false')), ('Example24G', 'test-only-password'))
        with self.assertRaises(RuntimeError):
            saved.profile_credentials(profile.format('true'))

    def test_multicast_destinations_carrying_credentials_are_not_in_repr(self):
        packets = easylink.data_packets(easylink.encode('Example24G', 'test-only-password', '192.0.2.20'))
        self.assertNotIn('239.126.', repr(packets))
        self.assertNotIn('test-only-password', repr(packets))

    def test_check_only_never_sends_or_prints_the_password(self):
        output = io.StringIO()
        with patch.object(sys, 'argv', ['send_saved_wifi.py', '--profile', 'Example24G',
                          '--interface-ip', '192.0.2.20', '--check-only']), \
             patch.object(saved, 'saved_password', return_value=('Example24G', 'test-only-password')), \
             patch.object(saved, 'send') as sender, patch('sys.stdout', output):
            self.assertEqual(saved.main(), 0)
            sender.assert_not_called()
        self.assertEqual(json.loads(output.getvalue())['status'], 'ready')
        self.assertNotIn('test-only-password', output.getvalue())


if __name__ == '__main__':
    unittest.main()
