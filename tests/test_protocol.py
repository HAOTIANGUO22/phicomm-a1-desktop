# SPDX-License-Identifier: GPL-3.0-only
import json
import socket
import struct
import unittest
import tempfile
import threading

from backend import Frames, Controller, DEFAULT_HEADER, FOOTER, control_frame, dns_answer, dns_question, validate_settings


class ProtocolTests(unittest.TestCase):
    def test_fragmented_and_coalesced_reports(self):
        messages = [{'datatype': 'mode', 'data': {'speed': 42, 'mode': 2}},
                    {'datatype': 'mode', 'data': {'speed': 42, 'mode': 0}}]
        wire = b''.join(DEFAULT_HEADER + json.dumps(m).encode() + FOOTER for m in messages)
        decoder = Frames()
        output = []
        for i in range(0, len(wire), 7):
            output.extend(decoder.feed(wire[i:i + 7]))
        self.assertEqual([m for _, m in output], messages)
        self.assertEqual(bytes(decoder.buffer), b'')

    def test_target_mac_and_command(self):
        wire = control_frame(45, 2, mac='020000000001')
        self.assertEqual(len(DEFAULT_HEADER), 28)
        self.assertEqual(wire[17:23], bytes.fromhex('020000000001'))
        self.assertEqual(json.loads(wire[28:-6]), {'datatype': 'control', 'data': {'speed': 45, 'mode': 2}})

    def test_invalid_control_is_rejected_before_sending(self):
        for kwargs in [{'speed': 29}, {'speed': 86}, {'mode': 3}, {}]:
            with self.assertRaises(ValueError):
                control_frame(**kwargs)

    def test_presets_send_explicit_speed_and_daily_remembers_manual_value(self):
        class Client:
            def __init__(self): self.frames = []
            def sendall(self, frame): self.frames.append(frame)
        with tempfile.TemporaryDirectory() as folder:
            controller = Controller(folder)
            controller.header = DEFAULT_HEADER
            controller.settings['manual_speed'] = 44
            client = controller.client = Client()
            for mode, speed in [(4, 30), (5, 85), (2, 44)]:
                controller.send(mode=mode)
                payload = json.loads(client.frames[-1][28:-len(FOOTER)])
                self.assertEqual(payload['data'], {'speed': speed, 'mode': mode})
            self.assertEqual(controller.settings['manual_speed'], 44)
            self.assertEqual(controller.pending_target, {'speed': 44, 'mode': 2})

    def test_power_on_sends_running_mode_and_speed_when_state_is_unknown(self):
        class Client:
            def sendall(self, frame): self.frame = frame
        with tempfile.TemporaryDirectory() as folder:
            controller = Controller(folder)
            controller.header = DEFAULT_HEADER
            controller.client = Client()
            controller.settings['manual_speed'] = 44
            controller.send(mode=1)
            self.assertEqual(json.loads(controller.client.frame[28:-6])['data'], {'speed': 44, 'mode': 1})
            self.assertEqual(controller.pending_target, {'speed': 44, 'mode': 2})
            self.assertTrue(controller.state['command_pending'])

    def test_repeated_confirmed_command_does_not_wait_for_nonexistent_change_report(self):
        class Client:
            def sendall(self, frame): pass
        with tempfile.TemporaryDirectory() as folder:
            controller = Controller(folder)
            controller.header = DEFAULT_HEADER
            controller.client = Client()
            controller.settings['manual_speed'] = 44
            controller.state.update(mode=2, speed=44, state_cached=False)
            controller.send(mode=1)
            self.assertFalse(controller.state['command_pending'])

    def test_reconnect_cache_stays_marked_as_historical(self):
        with tempfile.TemporaryDirectory() as folder:
            controller = Controller(folder)
            controller.header = DEFAULT_HEADER
            server, device = socket.socketpair()
            thread = threading.Thread(target=controller.read_control, args=(server, ('192.0.2.10', 1234)), daemon=True)
            thread.start()
            try:
                report = DEFAULT_HEADER + json.dumps({'datatype': 'mode', 'data': {'mode': 2, 'speed': 44}}).encode() + FOOTER
                device.sendall(report)
                with controller.condition:
                    self.assertTrue(controller.condition.wait_for(lambda: controller.state['last_seen'] is not None, timeout=2))
                snapshot = controller.snapshot()
                self.assertFalse(snapshot['state_cached'])
                restored = Controller(folder).snapshot()
                self.assertEqual((restored['mode'], restored['speed']), (2, 44))
                self.assertTrue(restored['state_cached'])
                self.assertFalse(restored['connected'])
            finally:
                device.close()
                thread.join(timeout=3)

    def test_network_settings_have_no_device_specific_defaults(self):
        with tempfile.TemporaryDirectory() as folder:
            controller = Controller(folder)
            for key in ('device_ip', 'server_ip', 'device_mac', 'gateway', 'dns_upstream'):
                self.assertEqual(controller.settings[key], '')
        with self.assertRaises(ValueError):
            validate_settings({})
        example = {'device_ip': '192.0.2.10', 'server_ip': '192.0.2.20',
                   'device_mac': '02:00:00:00:00:01', 'gateway': '192.0.2.1',
                   'dns_upstream': '', 'netmask': '255.255.255.0'}
        self.assertEqual(validate_settings(example)['device_mac'], '020000000001')
        self.assertEqual(validate_settings(example)['dns_upstream'], '192.0.2.1')

    def test_dns_override_is_only_for_vendor_domains(self):
        def query(name, qtype=1):
            labels = b''.join(bytes([len(p)]) + p.encode() for p in name.split('.')) + b'\0'
            return struct.pack('!HHHHHH', 123, 256, 1, 0, 0, 0) + labels + struct.pack('!HH', qtype, 1)
        packet = query('aircleanerconnecter.phicomm.com')
        answer = dns_answer(packet, '192.0.2.20')
        self.assertEqual(answer[:2], packet[:2])
        self.assertEqual(answer[-4:], socket.inet_aton('192.0.2.20'))
        self.assertIsNone(dns_answer(query('example.com'), '192.0.2.20'))
        self.assertEqual(struct.unpack_from('!H', dns_answer(query('aircleaner.phicomm.com', 28), '192.0.2.20'), 6)[0], 0)
        with self.assertRaises(ValueError):
            dns_question(b'bad')


if __name__ == '__main__':
    unittest.main()
