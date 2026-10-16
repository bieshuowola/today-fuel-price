import datetime as dt
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock
from zoneinfo import ZoneInfo
import health_watch as watch

NOW = dt.datetime(2026, 10, 17, 9, 0, tzinfo=ZoneInfo('Asia/Shanghai'))


def feed(hours=2):
    stamp=(NOW-dt.timedelta(hours=hours)).isoformat()
    return {'schema':5, 'generated_at':stamp,
            'health':{'index_ok':True,'checked_at':stamp}}


class WatchTests(unittest.TestCase):
    def test_normal_no_notification(self):
        sender=mock.Mock()
        with TemporaryDirectory() as directory:
            self.assertFalse(watch.run(now=NOW,fetcher=lambda _:feed(),
                sender=sender,topic='test-topic-123',path=Path(directory)/'state.json'))
        sender.assert_not_called()

    def test_stale_alert_is_rate_limited(self):
        sender=mock.Mock(return_value='ack')
        with TemporaryDirectory() as directory:
            path=Path(directory)/'state.json'
            options={'fetcher':lambda _:feed(19),'sender':sender,
                     'topic':'test-topic-123','path':path}
            self.assertTrue(watch.run(now=NOW,**options))
            self.assertFalse(watch.run(now=NOW+dt.timedelta(hours=3),**options))
            sender.assert_called_once()
            self.assertEqual(sender.call_args[0][1]['priority'],4)
            self.assertTrue(path.exists())

    def test_network_error_is_reported(self):
        errors=watch.inspect(NOW,fetcher=mock.Mock(side_effect=TimeoutError('offline')))
        self.assertIn('TimeoutError',errors[0])

    def test_failed_send_never_records_success(self):
        with TemporaryDirectory() as directory:
            path=Path(directory)/'state.json'
            with self.assertRaisesRegex(RuntimeError,'offline'):
                watch.run(now=NOW,fetcher=lambda _:feed(19),
                    sender=mock.Mock(side_effect=RuntimeError('offline')),
                    topic='test-topic-123',path=path)
            self.assertFalse(path.exists())

    def test_missing_topic_is_failure(self):
        with TemporaryDirectory() as directory:
            path=Path(directory)/'state.json'
            with self.assertRaisesRegex(RuntimeError,'NTFY_TOPIC'):
                watch.run(now=NOW,fetcher=lambda _:feed(19),path=path)
            self.assertFalse(path.exists())

if __name__=='__main__':
    unittest.main()
