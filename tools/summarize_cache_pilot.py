#!/usr/bin/env python3
"""Read-only evidence summary for a bounded Gemini cache pilot.

Usage: python3 tools/summarize_cache_pilot.py COST_FOLDER [--output NEW.json]
Prints JSON to stdout by default.  It neither contacts devices/providers nor
modifies the pilot folder; --output refuses to overwrite an existing file.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
import re
import sys
from typing import Any


def _read_json(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def _jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    try:
        for line in path.read_text().splitlines():
            value = json.loads(line)
            if isinstance(value, dict):
                rows.append(value)
    except (OSError, json.JSONDecodeError):
        pass
    return rows


def _number(value: Any) -> float | None:
    return float(value) if type(value) in (int, float) and math.isfinite(value) else None


def _keyword_id(row: dict[str, str], manifest: set[int]) -> int | None:
    """Audit CSV omits keyword_id; campaign IDs encode it as businessId*10000+id."""
    try:
        candidate = int(str(row.get('campaign_id', '')).strip()) % 10000
    except ValueError:
        return None
    return candidate if candidate in manifest else None


def _network(path: Path) -> dict[str, Any]:
    events = _jsonl(path)
    finished = [e for e in events if e.get('event') == 'resource_finished']
    cache_hits = sum(bool(e.get('served_from_cache') or e.get('from_disk_cache')
                          or e.get('from_service_worker')) for e in finished)
    encoded = [n for e in finished if (n := _number(e.get('encoded_bytes'))) is not None]
    stops = [e for e in events if e.get('event') == 'trace_stop']
    unfinished = stops[-1].get('unfinished_requests') if stops else None
    return {
        'path': str(path),
        'trace_stopped': bool(stops),
        'resource_finished': len(finished),
        'resource_failed': sum(e.get('event') == 'resource_failed' for e in events),
        'cache_hits': cache_hits,
        'encoded_bytes_finished': sum(encoded),
        'encoded_bytes_missing_count': len(finished) - len(encoded),
        'unfinished_requests': unfinished if type(unfinished) is int and unfinished >= 0 else None,
        'missing_early_events_possible': any(bool(e.get('missing_early_events_possible')) for e in events),
    }


def _cache_prepare(path: Path) -> dict[str, Any]:
    value = _read_json(path)
    if not isinstance(value, dict):
        return {'path': str(path), 'status': 'unreadable'}
    return {'path': str(path), 'status': 'ok' if value.get('ok') is True else 'failed',
            **{key: value.get(key) for key in ('reason', 'cache_reuse_verified',
                                                'http_cache_clear_requested', 'cookies_remaining')
               if key in value}}


def _gost_final_maxima(leg: Path) -> list[dict[str, Any]]:
    """Separate terminal/cumulative counters by process/service; never total them."""
    maxima: dict[tuple[str, Any, Any, str], dict[str, Any]] = {}
    for path in sorted(leg.glob('gost*.jsonl')):
        for event in _jsonl(path):
            # Terminal handler records are already per launched runner PID.
            if event.get('source') == 'terminal_socks5_handler_lower_bound':
                key = (path.name, event.get('pid'), None, str(event.get('service', 'unknown')))
                item = maxima.setdefault(key, {'source_file': path.name, 'pid': event.get('pid'),
                                                'gost_pid': None, 'service': event.get('service'),
                                                'kind': 'terminal_lower_bound', 'input_bytes': 0,
                                                'output_bytes': 0})
                for field in ('input_bytes', 'output_bytes'):
                    value = _number(event.get(field))
                    if value is not None: item[field] = max(item[field], int(value))
            # Metrics snapshots are cumulative, so retain the max per distinct PID/service.
            if event.get('source') == 'gost_metrics_cumulative' and isinstance(event.get('services'), list):
                for service in event['services']:
                    if not isinstance(service, dict):
                        continue
                    key = (path.name, event.get('pid'), event.get('gost_pid'), str(service.get('service', 'unknown')))
                    item = maxima.setdefault(key, {'source_file': path.name, 'pid': event.get('pid'),
                                                    'gost_pid': event.get('gost_pid'), 'service': service.get('service'),
                                                    'kind': 'cumulative_snapshot_max', 'input_bytes': 0,
                                                    'output_bytes': 0})
                    for field in ('input_bytes', 'output_bytes'):
                        value = _number(service.get(field))
                        if value is not None: item[field] = max(item[field], int(value))
    return list(maxima.values())


def summarize(folder: str | Path) -> dict[str, Any]:
    root = Path(folder).resolve()
    if not root.is_dir():
        raise ValueError('pilot folder does not exist')
    report = _read_json(root / 'report.json')
    report = report if isinstance(report, dict) else {}
    manifest_value = _read_json(root / 'keywords.json')
    manifest = [x for x in manifest_value if type(x) is int and x > 0] if isinstance(manifest_value, list) else []
    manifest_set = set(manifest)
    legs = []
    all_rows: list[dict[str, Any]] = []
    for leg in sorted(p for p in root.iterdir() if p.is_dir()):
        csv_paths = sorted(leg.glob('results*.csv'))
        rows = []
        for csv_path in csv_paths:
            try:
                with csv_path.open(newline='') as stream:
                    for row in csv.DictReader(stream):
                        item = {key: row.get(key, '') for key in ('campaign_id', 'biz_name', 'keyword', 'platform',
                                                                   'device', 'status', 'duration_s', 'rank_position',
                                                                   'rank_total', 'screenshot', 'error')}
                        item['keyword_id'] = _keyword_id(row, manifest_set)
                        item['csv_path'] = str(csv_path)
                        rows.append(item)
                        all_rows.append(item)
            except OSError:
                continue
        report_leg = next((x for x in report.get('legs', []) if isinstance(x, dict) and x.get('name') == leg.name), {})
        before, after = _number(report_leg.get('before_mb')), _number(report_leg.get('after_mb'))
        legs.append({'name': leg.name, 'report_status': report_leg.get('status', 'unreported'),
                     'evomi_before_mb': before, 'evomi_after_mb': after,
                     'evomi_delta_mb': before - after if before is not None and after is not None else None,
                     'csv_paths': [str(x) for x in csv_paths], 'completed_rows': len(rows),
                     'successful_rows': sum(r['status'].lower() == 'success' for r in rows),
                     'failure_rows': sum(r['status'].lower() != 'success' for r in rows),
                     'rows': rows, 'gost_final_maxima_separate_not_summed': _gost_final_maxima(leg)})
    by_keyword = {}
    for kid in manifest:
        prep = sorted(root.glob(f'**/cache_prepared_kw{kid}.json'))
        network = sorted(root.glob(f'**/network_kw{kid}.jsonl'))
        related = [r for r in all_rows if r['keyword_id'] == kid]
        by_keyword[str(kid)] = {'rows': related, 'cache_prepare': [_cache_prepare(p) for p in prep],
                                'network': [_network(p) for p in network],
                                'screenshot_paths': [r['screenshot'] for r in related if r['screenshot']]}
    completed_ids = {r['keyword_id'] for r in all_rows if r['keyword_id'] is not None}
    remaining = report.get('remaining_keyword_ids')
    if not isinstance(remaining, list):
        remaining = [kid for kid in manifest if kid not in completed_ids]
    return {'pilot_folder': str(root), 'report_status': report.get('status', 'missing'),
            'manifest_keyword_ids': manifest, 'remaining_keyword_ids': remaining,
            'legs': legs, 'per_keyword': by_keyword,
            'note': 'Evomi is provider billing; CDP encoded bytes/cache hits and GOST counters are separate evidence, not additive.'}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder')
    parser.add_argument('--output', type=Path, help='new JSON output path; stdout remains enabled')
    args = parser.parse_args()
    try:
        result = summarize(args.folder)
        payload = json.dumps(result, indent=2, sort_keys=True) + '\n'
        if args.output:
            if args.output.exists():
                raise ValueError('--output must be a new path')
            args.output.write_text(payload)
        sys.stdout.write(payload)
        return 0
    except (ValueError, OSError) as error:
        print(f'summarize_cache_pilot: {error}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
