#!/usr/bin/env python3
import json
import os
import sqlite3
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / 'config/avatar-factory.json').read_text(encoding='utf-8'))
DB = ROOT / CONFIG['paths']['workspace'] / 'avatar_factory.sqlite3'
BASE_URL = os.getenv('COCKPIT_URL', '').rstrip('/')
INGEST_KEY = os.getenv('FINOPS_INGEST_KEY', '')


def load_events():
    if not DB.exists():
        return []
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute('''
      SELECT c.id cost_id,c.category,c.provider,c.model,c.quantity,c.unit,c.cost_eur,c.metadata_json,c.created_at,
             j.id job_id,j.client_id,j.entity_id,j.project_id,j.character_id,j.billing_policy
      FROM costs c JOIN jobs j ON j.id=c.job_id
      ORDER BY c.id ASC
    ''').fetchall()
    conn.close()
    events = []
    for row in rows:
        r = dict(row)
        events.append({
            'event_key': f"avatar-factory:{r['job_id']}:{r['cost_id']}",
            'created_at': r['created_at'],
            'client_key': r['client_id'],
            'entity_key': r['entity_id'],
            'project_key': r['project_id'],
            'service_key': 'avatar-factory',
            'job_key': r['job_id'],
            'category': r['category'],
            'provider': r['provider'],
            'model': r['model'],
            'quantity': r['quantity'],
            'unit': r['unit'],
            'cost_eur': r['cost_eur'],
            'source': 'avatar-factory-local',
            'metadata': {
                **json.loads(r['metadata_json'] or '{}'),
                'character_id': r['character_id'],
                'local_billing_policy': r['billing_policy'],
                'billing_authority': 'cockpit-finops'
            },
        })
    return events


def sync_once():
    if not BASE_URL or not INGEST_KEY:
        print('FinOps sync disabled: COCKPIT_URL or FINOPS_INGEST_KEY missing')
        return False
    events = load_events()
    if not events:
        return True
    for i in range(0, len(events), 200):
        payload = json.dumps(events[i:i+200]).encode('utf-8')
        request = urllib.request.Request(
            f'{BASE_URL}/api/finops/events',
            data=payload,
            method='POST',
            headers={'Content-Type': 'application/json', 'x-finops-key': INGEST_KEY},
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            print(response.read().decode('utf-8'))
    return True


def main():
    watch = '--watch' in os.sys.argv
    if not watch:
        sync_once()
        return
    print('Avatar Factory FinOps sync loop started')
    while True:
        try:
            sync_once()
        except Exception as exc:
            print(f'FinOps sync error: {exc}')
        time.sleep(60)


if __name__ == '__main__':
    main()
