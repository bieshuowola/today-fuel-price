#!/usr/bin/env python3
"""Best-effort ntfy alerts for verified Fujian fuel-price changes.

A checked-in notification checkpoint prevents historical replay and most
duplicates. A server acceptance followed by a failed Git commit may still
produce a duplicate retry; FCM delivery is not guaranteed by server acceptance.
"""
from __future__ import annotations
import argparse
import datetime as dt
from decimal import Decimal, InvalidOperation
import json
import os
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
FEED = ROOT / 'data/latest.json'
CURSOR = ROOT / 'data/notify_state.json'
LOCAL_TZ = ZoneInfo('Asia/Shanghai')
NTFY_URL = 'https://ntfy.sh/'
SITE_URL = 'https://bieshuowola.github.io/today-fuel-price/'
ICON_URL = SITE_URL + 'icons/icon-192.png'


def amount(value):
    try:
        val = Decimal(str(value))
        if not val.is_finite() or not Decimal('0') < val < Decimal('30'):
            raise ValueError('out-of-range fuel price')
        return val.quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError('invalid fuel price') from exc


def date(value):
    if not isinstance(value, str):
        raise ValueError('invalid date')
    day = dt.date.fromisoformat(value)
    if day.isoformat() != value:
        raise ValueError('noncanonical date')
    return day


def load_feed(path=FEED):
    feed = json.loads(path.read_text(encoding='utf-8'))
    history = feed.get('history', [])
    if feed.get('schema') != 5 or not isinstance(history, list) or len(history) < 2:
        raise ValueError('unverified dataset')
    official = {}
    for item in history:
        if item.get('source') != 'official' or not str(item.get('url', '')).startswith(('https://fgw.fujian.gov.cn/', 'https://fgw.fj.gov.cn/')):
            raise ValueError('unverified official notice')
        key = date(item.get('day')).isoformat()
        prices = item.get('p', {})
        a, b = amount(prices['92']), amount(prices['95'])
        if not Decimal('4') < a < b < Decimal('22') or b-a >= 4 or key in official:
            raise ValueError('invalid official price or duplicate notice')
        official[key] = {'92': a, '95': b}
    newest = max(official)
    health = feed.get('health') or {}
    if not health.get('index_ok') or feed.get('latest_official_day') != newest or health.get('latest_official_day') != newest:
        raise ValueError('official verification is stale or missing')
    now = dt.datetime.now(LOCAL_TZ)
    checked = dt.datetime.fromisoformat(health['checked_at'])
    if checked.tzinfo is None or not 0 <= (now-checked).total_seconds() < 28800:
        raise ValueError('dataset was not verified in the last 8 hours')
    return feed, official, newest


def reference98(feed, notice_day):
    """Accept 98# only after the new tariff becomes effective."""
    current = feed.get('current') or {}
    ref = current.get('ref98') or {}
    try:
        effective = date(notice_day) + dt.timedelta(days=1)
        observed = date(ref.get('price_date'))
        p98 = amount(ref['p98'])
        if (observed < effective or observed > dt.datetime.now(LOCAL_TZ).date()
                or p98 != amount(current['p']['98'])
                or not Decimal('5') < p98 < Decimal('27')
                or ref.get('region') != '福建'
                or ref.get('source') not in ('澄曜 API', '极数本源')):
            return None
        if not feed.get('health', {}).get('api98_ok') or feed['health'].get('api98_source') != ref['source']:
            return None
        return {'value': p98, 'source': ref['source'], 'observed': observed}
    except (ValueError, TypeError, KeyError):
        return None


def previous98(feed, effective):
    previous = []
    for item in feed.get('obs98', []):
        try:
            d = date(item['day'])
            if d < effective and 5 < float(item['p']) < 27:
                previous.append((d, amount(item['p'])))
        except (KeyError, TypeError, ValueError):
            continue
    return max(previous, default=(None, None))[1]


def trend(deltas):
    if all(v > 0 for v in deltas):
        return '油价上调'
    if all(v < 0 for v in deltas):
        return '油价下调'
    return '油价调整'


def price_line(label, price, before=None):
    suffix = ''
    if before is not None:
        change = price-before
        if change > 0:
            suffix = f'（↑{change:.2f}元）'
        elif change < 0:
            suffix = f'（↓{-change:.2f}元）'
        else:
            suffix = '（不变）'
    return f'{label}号：{price:.2f}元/升{suffix}'


def official_message(newest, official, extra98=None, before98=None):
    days = sorted(official)
    pos = days.index(newest)
    if pos == 0:
        raise ValueError('no previous official baseline')
    previous = official[days[pos-1]]
    current = official[newest]
    deltas = [current[k]-previous[k] for k in ('92', '95')]
    if not any(deltas):
        return None
    effective = date(newest) + dt.timedelta(days=1)
    lines = ['【福建宁德｜官方调价】',
             price_line('92', current['92'], previous['92']),
             price_line('95', current['95'], previous['95'])]
    if extra98 is not None:
        lines.append(price_line('98', extra98['value'], before98) + '（第三方参考）')
        lines.append('98号为第三方参考价，非官方限价')
    else:
        lines.append('98号参考价待新周期核实')
    lines.extend([f'{effective.month}月{effective.day}日00:00起执行', '92/95来源：福建省发改委'])
    return {'title': '今日油价 · ' + trend(deltas), 'message': '\n'.join(lines), 'priority': 4}


def reference_message(notice_day, ref, prior):
    day = ref['observed']
    lines = ['【福建宁德｜98号第三方参考】',
             price_line('98', ref['value'], prior),
             f'报价日期：{day.month}月{day.day}日',
             f'数据来源：{ref["source"]}',
             '非官方限价，实际以加油站报价为准']
    return {'title': '今日油价 · 98号参考价更新', 'message': '\n'.join(lines), 'priority': 3}


def publish(topic, payload, opener=urllib.request.urlopen):
    if not isinstance(topic, str) or not 10 <= len(topic) <= 100 or not all(c.isascii() and (c.isalnum() or c in '-_') for c in topic):
        raise ValueError('invalid ntfy topic')
    data = {'topic': topic, **payload, 'click': SITE_URL, 'icon': ICON_URL}
    req = urllib.request.Request(NTFY_URL,
        data=json.dumps(data, ensure_ascii=False).encode('utf-8'),
        headers={'Content-Type': 'application/json; charset=utf-8', 'User-Agent': 'NingdeFuelAlert/1.0'}, method='POST')
    for attempt in range(3):
        try:
            with opener(req, timeout=16) as response:
                answer = json.load(response)
                if response.status != 200 or answer.get('event') != 'message' or answer.get('topic') != topic or not answer.get('id'):
                    raise RuntimeError('ntfy did not acknowledge delivery')
                return answer['id']
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt == 2:
                raise RuntimeError('ntfy publish network failure') from exc
            time.sleep(2 * (attempt+1))
    raise RuntimeError('ntfy publish not acknowledged')


def save_cursor(state, path=CURSOR):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(state, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    temp.replace(path)


def run(dry_run=False, feed_path=FEED, cursor_path=CURSOR, topic=None, sender=publish):
    feed, official, newest = load_feed(feed_path)
    if cursor_path.exists():
        cursor = json.loads(cursor_path.read_text(encoding='utf-8'))
        if cursor.get('schema') != 1:
            raise ValueError('unsupported notification cursor')
        last = date(cursor['last_official_day']).isoformat()
        last98 = date(cursor['last_98_cycle']).isoformat()
        if newest < last:
            raise ValueError('official history rollback: refusing to replay alerts')
    else:
        cursor = {'schema': 1, 'last_official_day': newest, 'last_98_cycle': newest}
        if not dry_run:
            save_cursor(cursor, cursor_path)
        print('Notification cursor initialized; historical prices not sent.')
        return []

    events = []
    ref = reference98(feed, newest)
    prior98 = previous98(feed, date(newest)+dt.timedelta(days=1))
    official_changed = newest > last
    if official_changed:
        official_event = official_message(newest, official, ref, prior98)
        if official_event:
            events.append(('official', official_event))
        else:
            cursor['last_98_cycle'] = newest
        cursor['last_official_day'] = newest
    elif last98 != newest and ref is not None:
        if prior98 is None or ref['value'] != prior98:
            events.append(('98', reference_message(newest, ref, prior98)))
        else:
            # Fresh quotation with the same 98 price is not a price change.
            cursor['last_98_cycle'] = newest

    if dry_run:
        for kind, event in events:
            print('DRY RUN:', kind, event['title'], repr(event['message']))
        return events

    if not events:
        if official_changed or cursor['last_98_cycle'] != last98:
            save_cursor(cursor, cursor_path)
        print('No new verified fuel-price event.')
        return []

    if not topic:
        raise RuntimeError('NTFY_TOPIC secret missing; alerts not sent and cursor not advanced')

    result = []
    for kind, event in events:
        identifier = sender(topic, event)
        print(f'ntfy accepted {kind} event for {newest}; message id: {identifier}')
        if kind == 'official' and ref is not None:
            cursor['last_98_cycle'] = newest
        if kind == '98':
            cursor['last_98_cycle'] = newest
        save_cursor(cursor, cursor_path)
        result.append(kind)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    try:
        run(dry_run=args.dry_run, topic=os.environ.get('NTFY_TOPIC'))
    except Exception as exc:
        print('Fuel-price alert failed:', exc, file=sys.stderr)
        sys.exit(1)
