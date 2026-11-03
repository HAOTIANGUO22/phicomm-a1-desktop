# SPDX-License-Identifier: GPL-3.0-only
from dataclasses import replace
import threading
import unittest
from unittest.mock import Mock, patch
from provisioning import Provisioner, discover, is_stock_a1, require_network
from windows_wifi import WifiAdapter, WifiError, subnet_for


def adapter():
    return WifiAdapter('01234567-89ab-cdef-0123-456789abcdef', 'Wi-Fi', 'Example adapter',
                       connected=True, profile='Example24G', ssid='Example24G',
                       ip='192.0.2.20', frequency=2437, profiles=['Example24G'])


def device():
    return {'ip': '192.0.2.30', 'config_read': True, 'PO': 'com.phicomm.basic',
            'FW': 'v1.47', 'HD': '3080B', 'N': 'EMW3080B(000001)'}


class FakeWifi:
    def __init__(self):
        self.credentials = Mock(return_value=('Example24G', 'test-only-password'))
        self.connect = Mock()
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def adapters(self): return [adapter()]


class ProvisioningTests(unittest.TestCase):
    def test_discovery_requires_a1_identity_and_matching_mac_suffix(self):
        self.assertTrue(is_stock_a1(device()))
        for changes in ({'config_read': False}, {'PO': 'unrelated'}, {'FW': 'other'}, {'N': 'Other device'}):
            self.assertFalse(is_stock_a1(dict(device(), **changes)))
        scanner = lambda ip: dict(device(), ip=ip)
        self.assertEqual(discover('192.0.2.30/32', checker=scanner,
                                 mac_reader=lambda ip: '020000000002'), [])
        found = discover('192.0.2.30/32', checker=scanner, mac_reader=lambda ip: '020000000001')
        self.assertTrue(found[0]['verified'])
        with self.assertRaises(WifiError): discover('192.0.0.0/16')

    def test_network_range_is_bounded_and_unusable_addresses_rejected(self):
        self.assertEqual(subnet_for('192.0.2.20', 16), '192.0.2.0/24')
        self.assertEqual(subnet_for('192.0.2.20', 28), '192.0.2.16/28')
        for ip in ('127.0.0.1', '169.254.1.2', '0.0.0.0', '239.1.1.1'):
            with self.assertRaises(WifiError): subnet_for(ip, 24)

    def test_network_must_be_connected_to_selected_profile_and_24ghz(self):
        require_network(adapter(), 'Example24G')
        for values in ({'connected': False}, {'profile': 'Other'}, {'ip': ''}, {'frequency': 5180}, {'frequency': 5975}):
            with self.assertRaises(WifiError): require_network(replace(adapter(), **values), 'Example24G')
        with self.assertRaises(WifiError): require_network(replace(adapter(), frequency=None), 'Example24G')
        require_network(replace(adapter(), frequency=None), 'Example24G', True)
        self.assertEqual(replace(adapter(), frequency=5975).band, '6 GHz')

    def test_already_online_never_reads_password_or_sends(self):
        wifi, sender = FakeWifi(), Mock()
        worker = Provisioner(wifi_factory=lambda: wifi, scanner=lambda *args: [device()], sender=sender)
        result = worker.run(adapter().guid, 'Example24G', threading.Event(), lambda *args: None)
        self.assertEqual(result['status'], 'already_online')
        wifi.credentials.assert_not_called()
        wifi.connect.assert_not_called()
        sender.assert_not_called()

    def test_cancelled_work_does_not_send(self):
        wifi, sender, cancel = FakeWifi(), Mock(), threading.Event()
        cancel.set()
        result = Provisioner(wifi_factory=lambda: wifi, sender=sender).run(
            adapter().guid, 'Example24G', cancel, lambda *args: None)
        self.assertEqual(result['status'], 'cancelled')
        wifi.credentials.assert_not_called()
        sender.assert_not_called()

    def test_connection_waits_for_old_5ghz_association_to_switch(self):
        wifi, cancel = FakeWifi(), threading.Event()
        wifi.adapters = Mock(side_effect=[[replace(adapter(), frequency=5180)],
                                          [replace(adapter(), frequency=5180)], [adapter()]])
        worker = Provisioner(wifi_factory=lambda: wifi, scanner=lambda *args: [device()])
        with patch.object(cancel, 'wait', return_value=False):
            result = worker.run(adapter().guid, 'Example24G', cancel, lambda *args: None)
        self.assertEqual(result['status'], 'already_online')
        self.assertEqual(wifi.adapters.call_count, 3)
        wifi.connect.assert_called_once()

    def test_sending_alone_is_not_reported_as_success(self):
        sender = Mock()
        worker = Provisioner(wifi_factory=FakeWifi, scanner=lambda *args: [], sender=sender,
                             duration=.01, verification_seconds=.01)
        result = worker.run(adapter().guid, 'Example24G', threading.Event(), lambda *args: None)
        self.assertEqual(result['status'], 'unconfirmed')
        sender.assert_called_once()

    def test_new_device_confirmation_stops_sender(self):
        scanner, cancel = Mock(side_effect=[[], [device()]]), threading.Event()
        worker = Provisioner(wifi_factory=FakeWifi, scanner=scanner, sender=Mock(),
                             duration=.01, verification_seconds=1)
        result = worker.run(adapter().guid, 'Example24G', cancel, lambda *args: None)
        self.assertEqual(result['status'], 'verified')
        self.assertTrue(cancel.is_set())

    def test_packet_destinations_are_not_exposed_in_error_messages(self):
        worker = Provisioner(wifi_factory=FakeWifi, scanner=lambda *args: [],
                             sender=Mock(side_effect=OSError('239.126.1.2')), duration=.01, verification_seconds=1)
        with self.assertRaises(WifiError) as caught:
            worker.run(adapter().guid, 'Example24G', threading.Event(), lambda *args: None)
        self.assertNotIn('239.126', str(caught.exception))


if __name__ == '__main__': unittest.main()
