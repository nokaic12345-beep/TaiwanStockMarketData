#!/usr/bin/env python3
"""Public TWSE/TPEx open-data daily OHLCV collector (no credentials).

The exchange OpenAPI returns the LATEST available trading day, not a requested date.
Never stamp the job's execution date onto price rows. Retain a dated archive and verify
actual provider dates. Public output contains no user-specific records or algorithms.
"""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime, date, timedelta, time, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
import urllib.request
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
DOCS = ROOT / 'docs'
SOURCES = {
    'twse': 'https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL',
    'tpex': 'https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes',
}
ATTRIBUTION = {
    'twse': 'https://data.gov.tw/dataset/11549',
    'tpex': 'https://data.gov.tw/dataset/11371',
}
CODE_RE = re.compile(r'^[0-9]{4}$')
ISO_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')


def parse_date(raw: object) -> str | None:
    value = str(raw or '').strip().replace('-', '').replace('/', '')
    if not value.isdigit(): return None
    try:
        if len(value) == 8:
            result = date(int(value[:4]), int(value[4:6]), int(value[6:8]))
        elif len(value) == 7:
            result = date(int(value[:3]) + 1911, int(value[3:5]), int(value[5:7]))
        else: return None
        return result.isoformat()
    except ValueError:
        return None


def get(row: dict, *keys: str) -> str:
    for key in keys:
        val = row.get(key)
        if val is not None and str(val).strip().lower() not in ('', 'null', 'none', '--'):
            return str(val).strip()
    return ''


def positive(raw: object) -> float | None:
    try:
        value = Decimal(str(raw or '').strip().replace(',', ''))
        if not value.is_finite(): return None
        return float(value)
    except (InvalidOperation, ValueError, TypeError):
        return None


def parse_row(row: dict, market: str) -> dict | None:
    code = get(row, 'Code', 'SecuritiesCompanyCode')
    if not CODE_RE.fullmatch(code): return None
    d = parse_date(get(row, 'Date'))
    if d is None: return None
    o = positive(get(row, 'OpeningPrice', 'Open'))
    h = positive(get(row, 'HighestPrice', 'High'))
    l = positive(get(row, 'LowestPrice', 'Low'))
    c = positive(get(row, 'ClosingPrice', 'Close'))
    vol = positive(get(row, 'TradeVolume', 'TradingShares', 'TradingVolume', 'TransactionVolume'))
    if any(x is None for x in (o, h, l, c, vol)): return None
    if min(o, h, l, c) <= 0 or vol < 0 or h < max(o, l, c) or l > min(o, h, c): return None
    return {'code': code, 'date': d, 'open': o, 'high': h, 'low': l, 'close': c, 'volume': vol}


def normalize(payload: list, market: str, today: date, current: time) -> tuple[str, list[dict]]:
    parsed = [r for row in payload if isinstance(row, dict) if (r := parse_row(row, market))]
    # Exchange endpoints may contain other securities. Only accept 4-digit codes;
    # the Android active-company universe is an additional filter.
    dates = Counter(x['date'] for x in parsed)
    if not dates: raise ValueError(f'{market}: no valid OHLCV rows')
    trading_date, _ = dates.most_common(1)[0]
    d = date.fromisoformat(trading_date)
    if d > today or (d == today and current < time(15, 30)):
        raise ValueError(f'{market}: data date {d} not final yet')
    if d < today - timedelta(days=16):
        raise ValueError(f'{market}: provider feed too stale ({d})')
    unique = {}
    for r in parsed:
        if r['date'] == trading_date: unique[r['code']] = r
    rows = [unique[k] for k in sorted(unique)]
    if len(rows) < 250: raise ValueError(f'{market}: only {len(rows)} unique valid 4-digit securities')
    return trading_date, rows


def fetch(url: str) -> list:
    request = urllib.request.Request(url, headers={'User-Agent': 'TWStockOpenDailySync/1.0 (+government-open-data-attribution)', 'Accept': 'application/json'})
    with urllib.request.urlopen(request, timeout=40) as response:
        if response.status != 200: raise RuntimeError(f'HTTP {response.status}')
        body = response.read(10_000_000)
    obj = json.loads(body)
    if not isinstance(obj, list): raise ValueError('expected JSON array')
    return obj


def write_json(path: Path, obj: object) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = (json.dumps(obj, ensure_ascii=False, separators=(',', ':'), sort_keys=True) + '\n').encode('utf-8')
    path.write_bytes(content)
    return hashlib.sha256(content).hexdigest()


def run(fetch_fn=fetch, now: datetime | None = None, root: Path=ROOT) -> dict:
    tz = ZoneInfo('Asia/Taipei')
    now = now or datetime.now(tz)
    now = now.astimezone(tz)
    docs = root / 'docs'
    docs.mkdir(exist_ok=True, parents=True)
    index_path = docs / 'market-index.json'
    try:
        previous = json.loads(index_path.read_text('utf-8'))
        if previous.get('schema') != 1: previous = {}
    except (FileNotFoundError, ValueError): previous = {}
    results = {}; failures = []
    for market, url in SOURCES.items():
        try:
            d, rows = normalize(fetch_fn(url), market, now.date(), now.time())
            path = docs / 'daily' / f'{d}.json'
            if path.exists():
                archive = json.loads(path.read_text('utf-8'))
                if archive.get('schema') != 1 or archive.get('date') != d:
                    raise ValueError('existing day archive has incompatible schema')
            else:
                archive = {'schema':1,'date':d,'markets':{}}
            archive['markets'][market] = {'source':url, 'license_dataset':ATTRIBUTION[market], 'rows':rows}
            write_json(path,archive)
            results[market] = {'date':d,'count':len(rows)}
        except Exception as e:
            failures.append(f'{market}: {type(e).__name__} {e}')
    # Preserve previously-verified market archives when provider fails or lags.
    day_entries=[]
    for p in sorted((docs / 'daily').glob('????-??-??.json')):
        d=p.stem
        if not ISO_RE.fullmatch(d): continue
        if date.fromisoformat(d) < now.date()-timedelta(days=210):
            p.unlink()
            continue
        try:
            archive=json.loads(p.read_text('utf-8'))
            market_counts={k:len(v.get('rows',[])) for k,v in archive.get('markets',{}).items() if k in SOURCES}
            if not market_counts: continue
            day_entries.append({'date':d,'path':f'daily/{p.name}','sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'markets':market_counts})
        except (ValueError, OSError): continue
    # Never claim latest market data from clock time; only observed dated archives.
    latest={}
    for market in SOURCES:
        valid=[x for x in day_entries if x['markets'].get(market,0)>=250]
        if valid: latest[market]=valid[-1]['date']
    success = bool(results)
    manifest={'schema':1, 'created_at_utc':now.astimezone(timezone.utc).isoformat().replace('+00:00','Z'),
              'latest_by_market':latest, 'days':day_entries, 'providers':SOURCES,
              'licensing':ATTRIBUTION, 'warning':failures}
    # If every source fails, retain the old manifest (and public timestamps) to avoid
    # incorrectly implying a fresh verification; Actions will fail visibly.
    if not success: raise RuntimeError('All sources failed; no publishing. ' + '; '.join(failures))
    write_json(index_path,manifest)
    return manifest


def main() -> None:
    p=argparse.ArgumentParser()
    p.add_argument('--root',type=Path,default=ROOT)
    args=p.parse_args()
    manifest=run(root=args.root)
    print('Latest dates:',manifest['latest_by_market'])
    print('Available archive days:',len(manifest['days']))
    if manifest['warning']:print('Warnings:', '; '.join(manifest['warning']))

if __name__=='__main__':main()
