import datetime as dt
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock
from zoneinfo import ZoneInfo

import notify_prices as n

TZ = ZoneInfo('Asia/Shanghai')


def fixture(changed=True, include98=False, stale98=False):
    now = dt.datetime.now(TZ)
    old = (now.date()-dt.timedelta(days=15)).isoformat()
    new = (now.date()-dt.timedelta(days=1)).isoformat()
    observed = (now.date()-dt.timedelta(days=1 if stale98 else 0)).isoformat()
    old_price={'92':8.00,'95':8.50}
    new_price={'92':8.20,'95':8.72} if changed else old_price
    def row(day,p):
        return {'day':day,'source':'official',
                'url':f'https://fgw.fujian.gov.cn/x/t{day.replace("-","")}_12.htm','p':p}
    feed={'schema':5,'history':[row(old,old_price),row(new,new_price)],
          'latest_official_day':new,
          'health':{'index_ok':True,'latest_official_day':new,'checked_at':now.isoformat(timespec='seconds'),
                    'api98_ok':include98,'api98_source':'极数本源' if include98 else None},
          'obs98':[{'day':old,'p':9.62,'source':'第三方多源参考'}]}
    if include98:
        feed['current']={'p':{'92':new_price['92'],'95':new_price['95'],'98':9.88},
                         'ref98':{'p98':9.88,'price_date':observed,'source':'极数本源','region':'福建'}}
        feed['obs98'].append({'day':observed,'p':9.88,'source':'极数本源'})
    return feed,old,new


class NotificationTests(unittest.TestCase):
    def case(self, folder, changed=True, include98=False, stale98=False):
        feed,old,new=fixture(changed,include98,stale98)
        path=Path(folder)/'latest.json'
        cursor=Path(folder)/'notify_state.json'
        path.write_text(json.dumps(feed,ensure_ascii=False),encoding='utf-8')
        return feed,old,new,path,cursor

    def test_publish_preserves_default_ntfy_icon_and_click(self):
        topic = 'test-topic-1234'
        response = mock.MagicMock()
        response.status = 200
        response.read.return_value = json.dumps({
            'event': 'message', 'topic': topic, 'id': 'ack-001'
        }).encode('utf-8')
        opener = mock.MagicMock()
        opener.return_value.__enter__.return_value = response
        payload = {'title': '今日油价 · 测试',
                   'message': '默认通知图标回归测试', 'priority': 4}
        self.assertEqual(n.publish(topic, payload, opener=opener), 'ack-001')
        request = opener.call_args.args[0]
        sent = json.loads(request.data.decode('utf-8'))
        self.assertNotIn('icon', sent)
        self.assertEqual(sent['click'], n.SITE_URL)
        self.assertEqual(sent['topic'], topic)
        self.assertEqual(sent['title'], payload['title'])
        self.assertEqual(sent['priority'], payload['priority'])

    def test_bootstrap_no_historical_notifications(self):
        with TemporaryDirectory() as d:
            _,old,new,path,cursor=self.case(d)
            sender=mock.Mock()
            self.assertEqual(n.run(feed_path=path,cursor_path=cursor,topic='test-topic-1234',sender=sender),[])
            self.assertEqual(json.loads(cursor.read_text())['last_official_day'],new)
            sender.assert_not_called()

    def test_official_update_once(self):
        with TemporaryDirectory() as d:
            _,old,new,path,cursor=self.case(d)
            n.save_cursor({'schema':1,'last_official_day':old,'last_98_cycle':old},cursor)
            sender=mock.Mock(return_value='ntfyack')
            self.assertEqual(n.run(feed_path=path,cursor_path=cursor,topic='test-topic-1234',sender=sender),['official'])
            message=sender.call_args[0][1]
            self.assertEqual(message['title'],'今日油价 · 油价上调')
            self.assertEqual(message['priority'],4)
            self.assertIn('92号：8.20元/升（↑0.20元）',message['message'])
            self.assertIn('95号：8.72元/升（↑0.22元）',message['message'])
            self.assertIn('00:00起执行',message['message'])
            self.assertEqual(n.run(feed_path=path,cursor_path=cursor,topic='test-topic-1234',sender=sender),[])
            sender.assert_called_once()

    def test_new_cycle_with_fresh_98_in_one_message(self):
        with TemporaryDirectory() as d:
            _,old,new,path,cursor=self.case(d,include98=True)
            n.save_cursor({'schema':1,'last_official_day':old,'last_98_cycle':old},cursor)
            sender=mock.Mock(return_value='ok')
            self.assertEqual(n.run(feed_path=path,cursor_path=cursor,topic='test-topic-1234',sender=sender),['official'])
            self.assertIn('98号：9.88元/升（↑0.26元）（第三方参考）',sender.call_args[0][1]['message'])
            self.assertEqual(json.loads(cursor.read_text())['last_98_cycle'],new)

    def test_delayed_98_reference_once(self):
        with TemporaryDirectory() as d:
            _,old,new,path,cursor=self.case(d,include98=True)
            n.save_cursor({'schema':1,'last_official_day':new,'last_98_cycle':old},cursor)
            sender=mock.Mock(return_value='ok')
            self.assertEqual(n.run(feed_path=path,cursor_path=cursor,topic='test-topic-1234',sender=sender),['98'])
            self.assertIn('98号：9.88元/升',sender.call_args[0][1]['message'])
            self.assertEqual(sender.call_args[0][1]['priority'],4)
            self.assertEqual(n.run(feed_path=path,cursor_path=cursor,topic='test-topic-1234',sender=sender),[])
            sender.assert_called_once()

    def test_old_98_quote_never_sent(self):
        with TemporaryDirectory() as d:
            _,old,new,path,cursor=self.case(d,include98=True,stale98=True)
            n.save_cursor({'schema':1,'last_official_day':new,'last_98_cycle':old},cursor)
            sender=mock.Mock()
            self.assertEqual(n.run(feed_path=path,cursor_path=cursor,topic='test-topic-1234',sender=sender),[])
            sender.assert_not_called()

    def test_failed_publish_keeps_checkpoint_for_retry(self):
        with TemporaryDirectory() as d:
            _,old,new,path,cursor=self.case(d)
            state={'schema':1,'last_official_day':old,'last_98_cycle':old}
            n.save_cursor(state,cursor)
            with self.assertRaises(RuntimeError):
                n.run(feed_path=path,cursor_path=cursor,topic='test-topic-1234',
                      sender=mock.Mock(side_effect=RuntimeError('offline')))
            self.assertEqual(json.loads(cursor.read_text()),state)

    def test_missing_secret_keeps_checkpoint(self):
        with TemporaryDirectory() as d:
            _,old,new,path,cursor=self.case(d)
            state={'schema':1,'last_official_day':old,'last_98_cycle':old}
            n.save_cursor(state,cursor)
            with self.assertRaisesRegex(RuntimeError,'NTFY_TOPIC'):
                n.run(feed_path=path,cursor_path=cursor)
            self.assertEqual(json.loads(cursor.read_text()),state)

    def test_no_price_change_no_alert(self):
        with TemporaryDirectory() as d:
            _,old,new,path,cursor=self.case(d,changed=False,include98=True)
            n.save_cursor({'schema':1,'last_official_day':old,'last_98_cycle':old},cursor)
            sender=mock.Mock()
            self.assertEqual(n.run(feed_path=path,cursor_path=cursor,topic='test-topic-1234',sender=sender),[])
            self.assertEqual(json.loads(cursor.read_text())['last_official_day'],new)
            sender.assert_not_called()

    def test_unchanged_new_cycle_98_quote_is_not_an_alert(self):
        with TemporaryDirectory() as d:
            feed,old,new,path,cursor=self.case(d,include98=True)
            feed['obs98'][0]['p']=9.88
            path.write_text(json.dumps(feed,ensure_ascii=False))
            n.save_cursor({'schema':1,'last_official_day':new,'last_98_cycle':old},cursor)
            sender=mock.Mock()
            self.assertEqual(n.run(feed_path=path,cursor_path=cursor,topic='test-topic-1234',sender=sender),[])
            self.assertEqual(json.loads(cursor.read_text())['last_98_cycle'],new)
            sender.assert_not_called()

    def test_stale_verification_rejected(self):
        with TemporaryDirectory() as d:
            feed,old,new,path,cursor=self.case(d)
            feed['health']['checked_at']=(dt.datetime.now(TZ)-dt.timedelta(hours=10)).isoformat()
            path.write_text(json.dumps(feed))
            with self.assertRaisesRegex(ValueError,'8 hours'):
                n.run(feed_path=path,cursor_path=cursor,topic='test-topic-1234')

    def test_downward_adjustment(self):
        event=n.official_message('2026-10-15',{
            '2026-10-01':{'92':n.amount(8.70),'95':n.amount(9.25)},
            '2026-10-15':{'92':n.amount(8.60),'95':n.amount(9.12)}})
        self.assertEqual(event['title'],'今日油价 · 油价下调')
        self.assertIn('10月16日00:00起执行',event['message'])

if __name__=='__main__':
    unittest.main()
