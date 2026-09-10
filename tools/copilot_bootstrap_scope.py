"""Explicit Copilot Wi-Fi-bootstrap scope.

The original measurement remains restricted to one of the two pilot phones.
Production rollout is separately gated by an explicit label allow-list so merely
setting the bootstrap flag can never fan out across the fleet.
"""
import os
import re


def selected_device():
    label=os.environ.get('COPILOT_ROLLOUT_DEVICE','device-104')
    devices={'device-104':'149145555W002883','device-106':'149145555W006477'}
    if label not in devices:raise ValueError('Copilot bootstrap measurement permits only104/106')
    return label,devices[label]


def device_allowed(label):
    rollout = os.environ.get('RANK_COPILOT_WIFI_ROLLOUT') == '1'
    if not rollout:
        return label == selected_device()[0]
    labels = {value.strip() for value in
              os.environ.get('RANK_COPILOT_WIFI_ROLLOUT_DEVICES', '').split(',')
              if value.strip()}
    if not labels or any(not re.fullmatch(r'device-\d{3}', value) for value in labels):
        raise ValueError('Copilot Wi-Fi rollout requires an explicit device-label allow-list')
    if 'device-125' in labels:
        raise ValueError('The protected test phone cannot enter the Copilot Wi-Fi rollout')
    if 'device-108' in labels and os.environ.get('RANK_ALLOW_QUARANTINED_DEVICE_108')!='1':
        raise ValueError('device-108 requires an explicit quarantine override')
    return label in labels
