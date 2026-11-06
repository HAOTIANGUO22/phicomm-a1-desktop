# SPDX-License-Identifier: GPL-3.0-only
import http.client
import json
import tempfile
import unittest
from unittest.mock import Mock

from backend import Controller, DEFAULT_HEADER, FOOTER
from ir_remote import IRRemote


class IRRemoteTests(unittest.TestCase):
    def setUp(self):
        folder = self.enterContext(tempfile.TemporaryDirectory())
        self.controller = Controller(folder)
        self.controller.settings['server_ip'] = '127.0.0.1'
        self.controller.settings['device_mac'] = '020000000001'
        self.controller.header = DEFAULT_HEADER
        self.controller.client = Mock()
        self.remote = IRRemote(self.controller)
        self.remote.start(port=0)
        self.addCleanup(self.remote.close)

    def post(self, code, token=None):
        host, port = self.remote.server.server_address
        connection = http.client.HTTPConnection(host, port, timeout=3)
        try:
            token = self.remote.token if token is None else token
            connection.request('POST', '/ir', code, {'Authorization': f'Bearer {token}'})
            return connection.getresponse().status
        finally:
            connection.close()

    def test_learning_persists_and_requires_valid_token(self):
        self.remote.learn('1')
        self.assertEqual(self.post('NEC:0000:0045', token='wrong'), 401)
        self.assertEqual(self.post('invalid'), 400)
        self.assertEqual(self.remote.keys, {})
        self.assertEqual(self.post('NEC:0000:0045'), 204)
        self.assertEqual(self.post('NEC:0000:0045'), 204)  # Repeat of the learning press
        self.controller.client.sendall.assert_not_called()
        self.remote.learn('0')
        self.remote.last_time = 0
        self.assertEqual(self.post('NEC:0000:0045'), 409)
        token = self.remote.token
        self.remote.close()
        self.remote = IRRemote(self.controller)
        self.remote.start(port=0)
        self.addCleanup(self.remote.close)
        self.assertEqual(self.remote.token, token)
        self.assertEqual(self.remote.keys, {'1': 'NEC:0000:0045'})

    def test_learned_sleep_button_sends_reference_frame(self):
        self.remote.learn('3')
        self.assertEqual(self.post('NEC:0000:0047'), 204)
        self.assertEqual(self.post('NEC:0001:0047'), 204)  # Same command from another address
        self.controller.client.sendall.assert_not_called()
        self.assertEqual(self.post('NEC:0000:0047'), 202)
        frame = self.controller.client.sendall.call_args.args[0]
        self.assertEqual(frame[17:23], bytes.fromhex('020000000001'))
        self.assertEqual(json.loads(frame[28:-len(FOOTER)])['data'], {'mode': 4, 'speed': 30})
        self.assertTrue(self.controller.snapshot()['command_pending'])

    def test_speed_key_needs_current_state_and_stays_in_range(self):
        self.remote.learn('↑')
        self.assertEqual(self.post('NEC:0000:0018'), 204)
        self.remote.last_time = 0
        self.controller.state.update(connected=True, mode=2, speed=83, state_cached=True)
        self.assertEqual(self.post('NEC:0000:0018'), 409)
        self.controller.client.sendall.assert_not_called()
        self.remote.last_time = 0
        self.controller.state['state_cached'] = False
        self.assertEqual(self.post('NEC:0000:0018'), 202)
        frame = self.controller.client.sendall.call_args.args[0]
        self.assertEqual(json.loads(frame[28:-len(FOOTER)])['data'], {'mode': 2, 'speed': 85})
