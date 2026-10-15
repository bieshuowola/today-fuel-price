import datetime as dt
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock
from zoneinfo import ZoneInfo
import update_feed as sync

NOTICE=lambda d: f'https://fgw.fujian.gov.cn/zfxxgkzl/zfxxgkml/yzdgkdqtxx/{d[:4]}{d[5:7]}/t{d.replace("-","")}_9999.htm'
DOC=lambda d,a='8.57',b='9.15':f'<p>自{d[:4]}年{int(d[5:7])}月{int(d[8:])}日24时起执行。</p><table><tr><td>车用92号汽油（ⅥB）</td><td>11000</td><td>{a}</td></tr><tr><td>车用95号汽油（ⅥB）</td><td>12000</td><td>{b}</td></tr></table>'
NOW=dt.datetime(2026,10,16,9,tzinfo=ZoneInfo('Asia/Shanghai'))

class SyncTests(unittest.TestCase):
 def test_official_price_column_and_effective_time(self):
  self.assertEqual(sync.parse_official('2026-09-24',NOTICE('2026-09-24'),DOC('2026-09-24'))['p'],{'92':8.57,'95':9.15})
  self.assertIsNone(sync.parse_official('2026-09-25',NOTICE('2026-09-24'),DOC('2026-09-24')))
  self.assertIsNone(sync.extract_prices(DOC('2026-09-24','8.57','12000')))
 def test_invalid_and_external_links_ignored(self):
  url=NOTICE('2026-10-29')
  page=f'<a href="{url}"><span>福建省发展和改革委员会</span>关于成品油价格调整的通告</a>'
  self.assertEqual(sync.extract_links(page)['2026-10-29'],url)
  self.assertFalse(sync.extract_links('<a href="https://evil.test/t20261029_11.htm">成品油价格调整</a>'))
 def test_original_fujian_baseline(self):
  h=sync.load_history()
  self.assertGreaterEqual(len(h),40)
  self.assertEqual(h['2026-09-24']['p'],{'92':8.57,'95':9.15})
 def test_index_freshness_rejects_stale_sources(self):
  h=sync.load_history()
  old=[h[k] for k in sorted(h)][-12:-1]
  listing=''.join(f'<a href="{r["url"]}">福建省发展和改革委员会关于成品油价格调整的通告</a>' for r in old)
  with mock.patch.object(sync,'fetch',return_value=listing):
   with self.assertRaisesRegex(RuntimeError,'索引滞后'):
    sync.official_scan(h,NOW)
 def test_homepage_catches_new_official_notice(self):
  h=sync.load_history()
  rows=[h[k] for k in sorted(h)][-12:]
  listing=''.join(f'<a href="{r["url"]}">福建省发展和改革委员会关于成品油价格调整的通告</a>' for r in rows[:-1])
  newest=rows[-1]
  home=f'<a href="{newest["url"]}">福建省发展和改革委员会关于成品油价格调整的通告</a>'
  def fetch(url,*args,**kwargs):
   if '/cpygg/' in url:return listing
   if url=='https://fgw.fujian.gov.cn/':return home
   if url in sync.INDEXES:raise RuntimeError('unavailable')
   if any(url==r['url'] for r in rows):
    r=next(r for r in rows if url==r['url'])
    return DOC(r['day'],str(r['p']['92']),str(r['p']['95']))
   raise RuntimeError('unavailable')
  with mock.patch.object(sync,'fetch',side_effect=fetch):
   result=sync.official_scan(h,NOW)
  self.assertTrue(result['index_ok'])
  self.assertGreaterEqual(result['source_count'],2)
 def test_failures_preserve_dataset(self):
  with TemporaryDirectory() as directory:
   out=Path(directory)/'latest.json'
   out.write_text('ORIGINAL')
   with mock.patch.object(sync,'OUT',out),mock.patch.object(sync,'NOW',return_value=NOW),mock.patch.object(sync,'fetch',side_effect=TimeoutError('offline')):
    with self.assertRaises(RuntimeError):sync.run()
   self.assertEqual(out.read_text(),'ORIGINAL')
 def test_api_stale_not_accepted(self):
  fixture={'code':200,'data':{'region':'福建宁德','updated':'2026/10/01','items':[{'name':'92号汽油','price':8.57},{'name':'95号汽油','price':9.15}]}}
  with mock.patch.object(sync,'fetch',return_value=json.dumps(fixture)):
   self.assertEqual(sync.get_current(NOW),(None,None))


 def test_98_validated_ruseo_quote(self):
  raw={'success':True,'list':[{'region':'福建省','date':'2026-09-24','gasoline_92':8.57,'gasoline_95':9.15,'gasoline_98':10.70}]}
  item=sync.parse_98_reference('ruseo',raw,{'92':8.57,'95':9.15},'2026-09-24',NOW)
  self.assertEqual(item['p98'],10.70)
  self.assertEqual(item['price_date'],'2026-09-24')

 def test_98_validated_apizero_quote(self):
  raw={'code':0,'data':{'province':'福建','update_date':'2026-09-24','prices':[
   {'type':'gasoline_92','price':8.57,'unit':'元/升'},
   {'type':'gasoline_95','price':9.15,'unit':'元/升'},
   {'type':'gasoline_98','price':10.70,'unit':'元/升'}]}}
  item=sync.parse_98_reference('apizero',raw,{'92':8.57,'95':9.15},'2026-09-24',NOW)
  self.assertEqual(item['p98'],10.70)

 def test_98_rejects_stale_discordant_or_wrong_region(self):
  base={'success':True,'list':[{'region':'福建','date':'2026-09-24','gasoline_92':8.57,'gasoline_95':9.15,'gasoline_98':10.70}]}
  for k,v in [('date','2026-07-01'),('gasoline_95',8.33),('region','广东')]:
   raw=json.loads(json.dumps(base));raw['list'][0][k]=v
   with self.assertRaises(ValueError):
    sync.parse_98_reference('ruseo',raw,{'92':8.57,'95':9.15},'2026-09-24',NOW)

 def test_98_fallback_provider_errors_are_nonfatal(self):
  with mock.patch.object(sync,'fetch_json_api',side_effect=RuntimeError('denied')):
   self.assertIsNone(sync.get_98_reference(NOW,{'92':8.57,'95':9.15},'2026-09-24'))

 def test_98_fallback_to_second_provider(self):
  bad={'success':False,'list':[]}
  good={'code':0,'data':{'province':'福建','update_date':'2026-09-24','prices':[
    {'type':'gasoline_92','price':8.57,'unit':'元/升'},
    {'type':'gasoline_95','price':9.15,'unit':'元/升'},
    {'type':'gasoline_98','price':10.7,'unit':'元/升'}]}}
  with mock.patch.object(sync,'fetch_json_api',side_effect=[bad,good]) as f:
   self.assertEqual(sync.get_98_reference(NOW,{'92':8.57,'95':9.15},'2026-09-24')['p98'],10.7)
   self.assertEqual(f.call_count,2)


 def test_98_historical_rows_need_official_tariff_agreement(self):
  page=('<table><tr><th>日期</th><th>92</th><th>95</th><th>98</th></tr>'
        '<tr><td>09-25</td><td>8.57</td><td>9.15</td><td>10.65</td></tr>'
        '<tr><td>09-12</td><td>8.25</td><td>8.81</td><td>10.31</td></tr>'
        '<tr><td>09-14</td><td>8.57</td><td>9.15</td><td>10.65</td></tr>'
        '<tr><td>09-25</td><td>8.57</td><td>9.15</td><td>10.65</td></tr></table>')
  obs=sync.parse_98_history_html(page,'https://www.autohome.com.cn/oil/350000.html',sync.load_history(),NOW)
  self.assertEqual([(r['day'],r['p']) for r in obs],[('2026-09-12',10.31),('2026-09-25',10.65)])

 def test_98_history_scraper_failure_is_nonfatal(self):
  with mock.patch.object(sync,'fetch',side_effect=TimeoutError('blocked')):
   self.assertEqual(sync.get_98_history(NOW,sync.load_history()),[])


if __name__=='__main__':unittest.main()
