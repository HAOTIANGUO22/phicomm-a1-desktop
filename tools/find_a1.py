# SPDX-License-Identifier: GPL-3.0-only
"""Discover stock MiCO configuration endpoints on the user's local /24."""
import concurrent.futures
import argparse
import ipaddress
import json
import socket
import urllib.request

SAFE_KEYS = {"name", "devicename", "device_name", "model", "product", "productid",
             "product_id", "mac", "mac_address", "macaddr", "version", "firmware",
             "firmware_revision", "software", "hardware"}


def identity_fields(value, output):
    if isinstance(value, dict):
        for key, item in value.items():
            if key.lower() in SAFE_KEYS and isinstance(item, (str, int)):
                output[key] = item
            elif isinstance(item, (dict, list)):
                identity_fields(item, output)
    elif isinstance(value, list):
        for item in value:
            identity_fields(item, output)


def check(address):
    address = str(address)
    try:
        with socket.create_connection((address, 8000), timeout=0.45):
            pass
    except OSError:
        return None
    result = {"ip": address, "port": 8000, "config_read": False}
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(f"http://{address}:8000/config-read", timeout=2) as response:
            body = response.read(65536)
        config = json.loads(body)
        result["config_read"] = True
        if isinstance(config, dict):
            for key in ('N', 'PO', 'HD', 'FW', 'RF'):
                if isinstance(config.get(key), (str, int)):
                    result[key] = config[key]
        identity_fields(config, result)
    except Exception:
        pass
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='查找自己局域网内的 MiCO 配置接口')
    parser.add_argument('--network', required=True, help='你自己的 IPv4 子网，例如 192.168.50.0/24')
    args = parser.parse_args()
    network = ipaddress.ip_network(args.network, strict=False)
    if network.version != 4 or network.num_addresses > 256:
        parser.error('请指定最多包含 256 个地址的 IPv4 子网')
    with concurrent.futures.ThreadPoolExecutor(max_workers=48) as pool:
        found = [r for r in pool.map(check, network.hosts()) if r]
    print(json.dumps({"endpoints": found}, ensure_ascii=True))
