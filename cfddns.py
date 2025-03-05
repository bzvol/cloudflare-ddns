#!/usr/bin/env python3

import requests
import json
import os
from datetime import datetime, timedelta


wd = os.path.dirname(os.path.abspath(__file__))


def get_now_str() -> str:
    """Get current date and time as a string."""
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def get_et_str(et: timedelta) -> str:
    """Get elapsed time as a string."""
    days = et.days
    hours = et.seconds / 3600
    return f"{days} days {hours:.2f} hours"


def log_change(current_ip: str, last_ip: str, et_last_changed: timedelta):
    """Log the IP change."""
    if not last_ip:
        return
    
    et_last_changed_str = get_et_str(et_last_changed)
    print(f"[{get_now_str()} INFO] IP changed from {last_ip} to {current_ip}, after {et_last_changed_str}")
    
    
def log_error(e: Exception):
    """Log the error."""
    print(f"[{get_now_str()} ERROR] {str(e)}")


class CloudflareDDNS:
    def __init__(self, config_file: str = f'{wd}/config.json'):
        # Load configuration
        with open(config_file, 'r') as f:
            config = json.load(f)

        self.api_token = config['api_token']
        if not self.api_token:
            raise Exception("API token is required")
        self.zone_id = config['zone_id']
        if not self.zone_id:
            raise Exception("Zone ID is required")
        self.domains = config['domains']
        if not self.domains:
            raise Exception("At least one domain is required")

        self.ip_cache_file = f'{wd}/last_ip.txt'
        self.cf_api_base = 'https://api.cloudflare.com/client/v4'

    def get_current_ip(self) -> str | None:
        """
        Get current public IP using multiple methods.
        Returns None if all methods fail.
        """
        ip_services = [
            'https://ifconfig.me/ip',
            'https://api.ipify.org',
            'https://icanhazip.com'
        ]

        for service in ip_services:
            try:
                response = requests.get(service, timeout=10)
                if response.status_code == 200:
                    return response.text.strip()
            except:
                continue

        return None

    def get_last_known_ip(self) -> tuple[str | None, timedelta | None]:
        """Get the last IP address from cache file."""
        try:
            with open(self.ip_cache_file, 'r') as f:
                last_ip, timestamp = f.read().strip().split(',')

                last_changed = datetime.fromisoformat(timestamp)
                et_last_changed = datetime.now() - last_changed

                return last_ip, et_last_changed
        except FileNotFoundError:
            return None, None

    def save_current_ip(self, ip: str):
        """Save the current IP to cache file."""
        with open(self.ip_cache_file, 'w') as f:
            f.write(f"{ip},{datetime.now().isoformat()}")

    def update_dns_records(self, new_ip: str) -> bool:
        """Update the DNS A records in Cloudflare."""
        # First, get the DNS record IDs
        headers = {
            'Authorization': f'Bearer {self.api_token}',
            'Content-Type': 'application/json'
        }

        # Get existing DNS records
        response = requests.get(
            f'{self.cf_api_base}/zones/{self.zone_id}/dns_records',
            headers=headers
        )

        if response.status_code != 200:
            raise Exception(f"Failed to get DNS records: {response.text}")

        records = response.json()['result']
        record_ids = []

        # Find the A record for our domain
        for record in records:
            if record['type'] == 'A' and record['name'] in self.domains:
                record_ids.append(record['id'])

        if not record_ids:
            raise Exception(f"No A record found for {self.domain}")

        # Update the record
        data = {
            'patches': [
                {
                    'id': record_id,
                    'content': new_ip
                }
                for record_id in record_ids
            ]
        }

        response = requests.post(
            f'{self.cf_api_base}/zones/{self.zone_id}/dns_records/batch',
            headers=headers,
            json=data
        )

        if response.status_code != 200:
            raise Exception(f"Failed to update DNS records: {response.text}")

        return True

    def run(self):
        """Main execution logic."""
        try:
            current_ip = self.get_current_ip()
            if not current_ip:
                raise Exception("Could not determine current IP address")

            last_ip, et_last_changed = self.get_last_known_ip()

            if current_ip != last_ip:
                log_change(current_ip, last_ip, et_last_changed)
                self.update_dns_records(current_ip)
                self.save_current_ip(current_ip)

        except Exception as e:
            log_error(e)


if __name__ == "__main__":
    ddns = CloudflareDDNS()
    ddns.run()
