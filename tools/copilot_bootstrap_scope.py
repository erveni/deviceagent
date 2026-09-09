"""Explicit measured rollout scope. Never accepts arbitrary fleet devices."""
import os


def selected_device():
    label=os.environ.get('COPILOT_ROLLOUT_DEVICE','device-104')
    devices={'device-104':'149145555W002883','device-106':'149145555W006477'}
    if label not in devices:raise ValueError('Copilot bootstrap measurement permits only104/106')
    return label,devices[label]


def device_allowed(label):
    return label==selected_device()[0]
