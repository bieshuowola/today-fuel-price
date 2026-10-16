#!/usr/bin/env python3
"""Watch the public dashboard, alert on long stalls, never on unchanged prices."""
import datetime as dt
import json
import os
from pathlib import Path
import time
import urllib.request
from zoneinfo import ZoneInfo
from notify_prices import publish

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / 'data/watchdog_state.json'
FEED_URL = 'https://bieshuowola.github.io/today-fuel-price/data/latest.json'
NOW = lambda: dt.datetime.now(ZoneInfo('Asia/Shanghai'))
STALE_HOURS = 15
ALERT_COOLDOWN_HOURS = 24


def read_public(url, opener=urllib.request.urlopen):
    req = urllib.request.Request(url, headers={'Cache-Control': 'no-cache',
                         'User-Agent': 'NingdeFuelWatchdog/1.0'})
    with opener(req, timeout=18) as res:
        if res.status != 200:
            raise RuntimeError('Unexpected HTTP status')
        return json.loads(res.read(180_000).decode('utf-8'))


def inspect(now=None, fetcher=read_public):
    now = now or NOW()
    try:
        feed = fetcher(FEED_URL + '?t=' + str(int(now.timestamp())))
        if feed['schema'] != 5 or not feed['health']['index_ok']:
            raise ValueError('Invalid public verification status')
        checked = dt.datetime.fromisoformat(feed['health']['checked_at'])
        generated = dt.datetime.fromisoformat(feed['generated_at'])
        ages = [(now - checked).total_seconds()/3600,
                (now - generated).total_seconds()/3600]
        if any(a < -0.1 for a in ages):
            raise ValueError('Public data contains a future timestamp')
        if any(a > STALE_HOURS for a in ages):
            return ['网站公开数据或官方核验超过15小时没有更新']
        return []
    except Exception as exc:
        return ['网站公开油价数据无法核验：' + type(exc).__name__]


def run(now=None, fetcher=read_public, sender=publish, path=STATE, topic=None):
    now = now or NOW()
    problems = inspect(now, fetcher)
    if not problems:
        print('Watchdog OK: published data and verification are recent.')
        return False
    state = json.loads(path.read_text('utf-8')) if path.exists() else {}
    recent = state.get('last_alert_at')
    if recent:
        sent = dt.datetime.fromisoformat(recent)
        if dt.timedelta() <= now - sent < dt.timedelta(hours=ALERT_COOLDOWN_HOURS):
            print('Stall remains; already alerted within 24 hours.')
            return False
    if not topic:
        raise RuntimeError('NTFY_TOPIC secret missing during failure alert')
    payload = {
        'title': '今日油价 · 自动同步异常',
        'message': '【运行状态告警，不是调价】\n' + '\n'.join(problems)
            + '\n请检查 GitHub Actions，同步恢复前不要依赖自动调价通知。',
        'priority': 4
    }
    message_id = sender(topic, payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps({'schema': 1, 'last_alert_at': now.isoformat(timespec='seconds')},
                               ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    temp.replace(path)
    print('ntfy acknowledged watchdog alert:', message_id)
    return True


if __name__ == '__main__':
    run(topic=os.environ.get('NTFY_TOPIC'))
