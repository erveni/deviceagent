"""Explicit allow-list for production cache-preserving ranking."""
import os,re


def device_allowed(label):
    if os.environ.get('RANK_CACHE_LOW_COST_ROLLOUT')!='1':return False
    labels={x.strip() for x in os.environ.get('RANK_CACHE_LOW_COST_DEVICES','').split(',') if x.strip()}
    if not labels or any(not re.fullmatch(r'device-\d{3}',x) for x in labels):
        raise ValueError('Cache rollout requires an explicit device allow-list')
    if 'device-125' in labels:raise ValueError('Protected test phone cannot enter cache rollout')
    return label in labels
