"""Explicit v83 combined trial; legacy v82 cache experiments remain unchanged."""


def cache_health_allowed(health, evidence=False):
    expected = 83 if evidence else 82
    return (type(health.get('versionCode')) is int
            and health['versionCode'] == expected
            and health.get('accessibility') is True)
