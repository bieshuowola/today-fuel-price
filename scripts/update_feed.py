#!/usr/bin/env python3
"""福建成品油公告价同步。官方抓取失败时绝不以新的成功时间覆写旧数据。"""
from __future__ import annotations
import datetime as dt
import html
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
import time
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'data'/'official_history.json'
OUT=ROOT/'data'/'latest.json'
INDEXES=('https://fgw.fujian.gov.cn/ztzl/fjswjj/cpygg/', 'https://fgw.fujian.gov.cn/', 'https://fgw.fujian.gov.cn/zwgk/gsgg/', 'https://fgw.fj.gov.cn/ztzl/fjswjj/cpygg/')
API='https://60s.viki.moe/v2/fuel-price?region='
BJT=ZoneInfo('Asia/Shanghai')
HEADERS={'User-Agent':'Mozilla/5.0 (compatible; NingdeFuelDashboard/4.2; public price notices)', 'Accept':'text/html,application/json'}
DOC_URL=re.compile(r'^https://fgw\.(?:fujian|fj)\.gov\.cn/.*/t(20\d{6})_\d+\.html?$',re.I)
DATE=re.compile(r'(20\d{2})[-/年.]\s*(\d{1,2})[-/月.]\s*(\d{1,2})')
NOW=lambda:dt.datetime.now(BJT)

def fetch(url:str, timeout=13)->str:
    last=None
    for attempt in range(3):
        try:
            req=urllib.request.Request(url,headers=HEADERS)
            with urllib.request.urlopen(req,timeout=timeout) as resp:
                if resp.status != 200: raise RuntimeError(f'HTTP {resp.status}')
                raw=resp.read(3_500_000)
                charset=resp.headers.get_content_charset() or 'utf-8'
                return raw.decode(charset,'replace')
        except Exception as e:
            last=e
            if attempt<2:time.sleep(.3*(attempt+1))
    raise RuntimeError(f'{url}: {last}')

def iso_date(s):
    m=DATE.search(str(s or ''))
    if not m:return None
    try:return dt.date(*(int(v) for v in m.groups())).isoformat()
    except ValueError:return None

def valid_prices(p):
    try:
        a,b=float(p['92']),float(p['95'])
        return 4<a<18 and a<b<22 and (b-a)<4
    except (ValueError,KeyError,TypeError):return False

class NoticeLinks(HTMLParser):
    def __init__(self,base_url):
        super().__init__(convert_charrefs=True)
        self.base_url=base_url;self.links={};self.current=None;self.chars=[]
    def handle_starttag(self,tag,attrs):
        if tag!='a':return
        data=dict(attrs);href=data.get('href','')
        u=urllib.parse.urljoin(self.base_url,href)
        m=DOC_URL.match(u)
        if not m:return
        self.current=(m[1],u,data.get('title',''));self.chars=[]
    def handle_data(self,value):
        if self.current:self.chars.append(value)
    def handle_endtag(self,tag):
        if tag=='a' and self.current:
            day,u,title=self.current
            label=title+' '+' '.join(self.chars)
            if '成品油价格调整' in label:
                self.links[f'{day[:4]}-{day[4:6]}-{day[6:8]}']=u
            self.current=None;self.chars=[]

def extract_links(page,base_url=INDEXES[0]):
    p=NoticeLinks(base_url);p.feed(page)
    return p.links

def extract_prices(page):
    rows=re.findall(r'<tr\b[^>]*>(.*?)</tr>',page,re.I|re.S)
    prices={}
    for row in rows:
        cells=[html.unescape(re.sub(r'<[^>]*>',' ',c)).replace('\xa0',' ') for c in re.findall(r'<t[dh]\b[^>]*>(.*?)</t[dh]>',row,re.I|re.S)]
        if len(cells)<3:continue
        label=re.sub(r'\s+','',cells[0]);m=re.search(r'(92|95)号汽油',label)
        if not m:continue
        numbers=re.findall(r'\d+(?:\.\d+)?',cells[2])
        if numbers:prices[m[1]]=float(numbers[0])
    return prices if valid_prices(prices) else None

def parse_official(day,url,page):
    plain=html.unescape(re.sub(r'<[^>]+>',' ',page)).replace('\xa0',' ')
    m=re.search(r'自\s*(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日\s*24\s*时\s*起\s*执行',plain)
    if not m:return None
    effective=f'{int(m[1]):04d}-{int(m[2]):02d}-{int(m[3]):02d}'
    if effective!=day or not DOC_URL.match(url):return None
    p=extract_prices(page)
    if not p:return None
    return {'day':day,'p':{'92':p['92'],'95':p['95']},'source':'official','url':url}

def load_history():
    rows={}
    for path in (BASE,OUT):
        if not path.exists():continue
        try:obj=json.loads(path.read_text(encoding='utf-8'))
        except (OSError,ValueError):
            print('忽略不可解析的本地历史文件：'+str(path),file=sys.stderr)
            continue
        arr=obj if isinstance(obj,list) else obj.get('history',[])
        for r in arr:
            if not isinstance(r,dict) or r.get('source')!='official' or not valid_prices(r.get('p',{})) or not DOC_URL.match(str(r.get('url',''))):continue
            day=r.get('day');url_date=DOC_URL.match(r['url'])[1]
            if iso_date(day)!=day or day.replace('-','')!=url_date:continue
            rows[day]={'day':day,'p':{'92':float(r['p']['92']),'95':float(r['p']['95'])},'source':'official','url':r['url']}
    return rows

def official_scan(history, now):
    errors=[];links={};healthy_sources=0
    for url in INDEXES:
        try:
            found=extract_links(fetch(url),url)
            if not found:raise RuntimeError('未识别到成品油公告链接')
            links.update(found)
            healthy_sources+=1
        except Exception as e:errors.append(url+' '+str(e))
    if healthy_sources==0 or len(links)<10:
        raise RuntimeError('官方公告索引不可用或条目不足：'+'; '.join(errors))
    if max(links)<max(history):
        raise RuntimeError(f'官方索引滞后：索引最新 {max(links)}，既有基线最新 {max(history)}，拒绝假成功')
    pending=[];today=now.date()
    for day,url in sorted(links.items()):
        date=dt.date.fromisoformat(day)
        if date>today:continue
        if day not in history or (today-date).days<=35:
            pending.append((day,url))
    for day,url in pending:
        candidate=parse_official(day,url,fetch(url))
        if candidate is None:raise RuntimeError(f'官方公告无法校验：{day}, {url}')
        old=history.get(day)
        if old and old['p'] != candidate['p']:
            print('官方公告价格修正:',day,old['p'],'->',candidate['p'])
        history[day]=candidate
    latest=max(history)
    age=(today-dt.date.fromisoformat(latest)).days
    return {'checked_at':now.isoformat(timespec='seconds'),'index_ok':True,'link_count':len(links),'source_count':healthy_sources,'source_errors':errors[-3:],'verified_count':len(pending),'latest_official_day':latest,'latest_official_age_days':age}

def forecast_from_api(trend,asof,today):
    if not isinstance(trend,dict):return None
    direction=trend.get('direction')
    if direction not in ('上调','下调','搁浅','不调'):return None
    m=re.search(r'(?:(20\d{2})年)?\s*(\d{1,2})月\s*(\d{1,2})日',str(trend.get('next_adjustment_date','')))
    if not m:return None
    try:day=dt.date(int(m[1] or today.year),int(m[2]),int(m[3]))
    except ValueError:return None
    if not today<=day<=today+dt.timedelta(days=45):return None
    result={'window':day.isoformat(),'direction':direction,'asof':asof,'source':'60s 油价预测（第三方）','url':'https://docs.60s-api.viki.moe/376793576e0'}
    try:
        a,b=float(trend['change_liter_min']),float(trend['change_liter_max'])
        if 0<=a<=b<2:result['range']=[a,b]
    except (ValueError,TypeError,KeyError):pass
    return result

def get_current(now):
    errors=[]
    for region in ('福建宁德','福建'):
        try:
            j=json.loads(fetch(API+urllib.parse.quote(region)))
            data=j.get('data') or {}
            if j.get('code')!=200 or not re.search(r'福建|宁德',str(data.get('region',''))):raise ValueError('地区错误')
            p={}
            for item in data.get('items',[]):
                m=re.match(r'^(92|95|98)',str(item.get('name','')))
                if m:p[m[1]]=float(item['price'])
            if not valid_prices(p):raise ValueError('无效价格')
            asof=iso_date(data.get('updated'))
            if not asof:raise ValueError('未提供有效更新时间')
            delta=(now.date()-dt.date.fromisoformat(asof)).days
            if not 0<=delta<=3:raise ValueError(f'第三方报价已过期 {delta} 天')
            forecast=forecast_from_api(data.get('trend'),asof,now.date())
            current={'p':p,'asof':asof,'source':'60s 油价 API','region':str(data.get('region'))}
            return current,forecast
        except Exception as e:errors.append(region+' '+str(e))
    print('第三方 API 未获取可用数据：'+'；'.join(errors),file=sys.stderr)
    return None,None


def fetch_json_api(url, payload=None, timeout=11):
    """Fetch a publicly documented oil-price API; JSON is data, never code."""
    headers={'User-Agent':'NingdeFuelDashboard/4.5 (+public price reference)',
             'Accept':'application/json'}
    content=None
    if payload is not None:
        content=json.dumps(payload,ensure_ascii=False).encode('utf-8')
        headers['Content-Type']='application/json; charset=utf-8'
    req=urllib.request.Request(url,data=content,headers=headers)
    with urllib.request.urlopen(req,timeout=timeout) as response:
        if response.status!=200:raise RuntimeError(f'HTTP {response.status}')
        data=response.read(160_000)
        if len(data)>=160_000:raise ValueError('第三方响应超过大小限制')
    obj=json.loads(data.decode('utf-8'))
    if not isinstance(obj,dict):raise ValueError('第三方响应不是JSON对象')
    return obj

def parse_98_reference(provider, obj, official_prices, official_day, now):
    """Only accept fresh-for-current-cycle Fujian quotes corroborated by official 92/95."""
    if provider=='ruseo':
        if obj.get('success') is not True or not isinstance(obj.get('list'),list):
            raise ValueError('澄曜API未返回有效油价列表')
        rows=[r for r in obj['list'] if isinstance(r,dict) and '福建' in str(r.get('region',''))]
        if len(rows)!=1:raise ValueError('澄曜API福建报价缺失或重复')
        row=rows[0]
        raw={'92':row.get('gasoline_92'),'95':row.get('gasoline_95'),'98':row.get('gasoline_98')}
        region=row.get('region','')
        stamp=row.get('date')
        name='澄曜 API'
        link='https://api.ruseo.cn/api-doc/oilprice'
    elif provider=='apizero':
        if obj.get('code')!=0 or not isinstance(obj.get('data'),dict):
            raise ValueError('极数本源未返回成功结果')
        data=obj['data']
        raw={}
        for item in data.get('prices',[]):
            if not isinstance(item,dict) or item.get('type') not in ('gasoline_92','gasoline_95','gasoline_98'):continue
            if item.get('unit')!='元/升':raise ValueError('第三方数据单位错误')
            raw[item['type'][-2:]]=item.get('price')
        region=data.get('province','')
        stamp=data.get('update_date')
        name='极数本源'
        link='https://apizero.cn/aidocs/oil-price'
    else:raise ValueError('未知的报价来源')
    if '福建' not in str(region):raise ValueError('第三方报价地区不是福建')
    source_day=iso_date(stamp)
    if not source_day or not official_day or source_day<official_day or source_day>now.date().isoformat():
        raise ValueError(f'第三方价格日期不在当前已核验调价周期内: {source_day}')
    try:
        p={k:float(raw[k]) for k in ('92','95','98')}
    except (TypeError,ValueError,KeyError) as e:raise ValueError('第三方报价缺少有效的92/95/98价格') from e
    if not valid_prices(p) or not p['95']+0.10 <= p['98'] <= p['95']+6.0:
        raise ValueError('98号参考价格未通过合理范围检查')
    if any(abs(p[k]-official_prices[k])>0.04 for k in ('92','95')):
        raise ValueError('第三方92/95号报价与福建官方限价不一致')
    return {'p98':round(p['98'],2),'source':name,'url':link,'price_date':source_day,
            'checked_at':now.isoformat(timespec='seconds'),'region':'福建'}

def get_98_reference(now,official_prices,official_day):
    """Independent best-effort 98# feed: failure never affects official synchronization."""
    sources=(('ruseo','https://api.ruseo.cn/api/oilprice',None),
             ('apizero','https://v1.apizero.cn/api/oil-price',{'province':'福建'}))
    errors=[]
    for provider,url,payload in sources:
        try:
            raw=fetch_json_api(url,payload)
            offer=parse_98_reference(provider,raw,official_prices,official_day,now)
            print('98号来源已核对：',offer['source'],'原始数据日期',offer['price_date'])
            return offer
        except Exception as e:
            errors.append(provider+': '+str(e))
    print('98号第三方报价未通过核验，保留空值或旧快照：'+'；'.join(errors),file=sys.stderr)
    return None


class HistoryTableReader(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows=[];self.row=None;self.cell=None
    def handle_starttag(self,tag,attrs):
        if tag=='tr':self.row=[]
        elif tag in ('td','th') and self.row is not None:self.cell=[]
    def handle_data(self,value):
        if self.cell is not None:self.cell.append(value)
    def handle_endtag(self,tag):
        if tag in ('td','th') and self.cell is not None and self.row is not None:
            self.row.append(re.sub(r'\s+',' ',''.join(self.cell)).strip());self.cell=None
        elif tag=='tr' and self.row is not None:
            self.rows.append(self.row);self.row=None;self.cell=None

def parse_98_history_html(page,url,history,now):
    """Only trust rows whose 92/95 match effective official Fujian prices."""
    parser=HistoryTableReader();parser.feed(page)
    accepted=[]
    for cells in parser.rows:
        if len(cells)<4:continue
        m=re.search(r'(?<!\d)(?:(20\d{2})[-/])?(\d{1,2})[-/](\d{1,2})(?!\d)',cells[0])
        if not m:continue
        year=int(m[1] or now.year);mon=int(m[2]);day=int(m[3])
        if m[1] is None and (mon,day)>(now.month,now.day):year-=1
        try:at=dt.date(year,mon,day)
        except ValueError:continue
        if at>now.date() or at<now.date()-dt.timedelta(days=740):continue
        values=[]
        for cell in cells[1:4]:
            n=re.search(r'(?<!\d)(\d{1,2}(?:\.\d{1,2})?)(?!\d)',cell)
            if not n:break
            values.append(float(n[1]))
        if len(values)!=3:continue
        p92,p95,p98=values
        effective=[day for day in history if day<at.isoformat()]
        if not effective:continue
        official=history[max(effective)]['p']
        if abs(p92-official['92'])>0.04 or abs(p95-official['95'])>0.04:continue
        if not p95+.10<=p98<=p95+6:continue
        accepted.append({'day':at.isoformat(),'p':round(p98,2),'source':'第三方历史参考','url':url})
    return sorted({r['day']:r for r in accepted}.values(),key=lambda x:x['day'])

def get_98_history(now,history):
    for url in ('https://www.autohome.com.cn/oil/350000.html',
                'https://www.756657.com/fujian/'):
        try:
            found=parse_98_history_html(fetch(url,timeout=9),url,history,now)
            if len(found)>=4:
                print('98号历史核验成功:',len(found),'条，来源',url,'日期',found[0]['day'],found[-1]['day'])
                return found
            print('98号历史数据不足:',url,len(found),file=sys.stderr)
        except Exception as e:
            print('98号历史来源暂时不可用:',url,str(e),file=sys.stderr)
    return []

def run():
    now=NOW();old={}
    if OUT.exists():
        try:old=json.loads(OUT.read_text(encoding='utf-8'))
        except (ValueError,OSError):pass
    history=load_history()
    if not history:raise RuntimeError('官方历史基线丢失')
    health=official_scan(history,now)
    current,forecast=get_current(now)
    last_effective=max(k for k in history if k<now.date().isoformat())
    verified_98=get_98_reference(now,history[last_effective]['p'],last_effective)
    if verified_98:
        # Preserve the authoritative 92/95 quotes. The extra 98 quote is a
        # dated, provincial third-party observation — not a government ceiling.
        p=dict(history[last_effective]['p'])
        p['98']=verified_98['p98']
        current={'p':p,'asof':now.date().isoformat(),'source':'98号第三方参考',
                 'region':'福建宁德','ref98':verified_98}
    if current is None:
        cached=old.get('current')
        if isinstance(cached,dict):current=cached
    by_day={}
    for r in old.get('obs98') or []:
        if not isinstance(r,dict) or iso_date(r.get('day'))!=r.get('day'):continue
        try:value=float(r.get('p',0))
        except (ValueError,TypeError):continue
        if 5<value<27:by_day[r['day']]={'day':r['day'],'p':value,'source':r.get('source','第三方参考'),'url':r.get('url','')}
    for row in get_98_history(now,history):
        previous=by_day.get(row['day'])
        if previous is None:by_day[row['day']]=row
        elif abs(previous['p']-row['p'])>0.04:
            print('拒绝98号历史数据冲突:',row['day'],file=sys.stderr)
    if current and '98' in current.get('p',{}) and current.get('asof'):
        day=current['asof'];value=float(current['p']['98'])
        if 5<value<27 and (verified_98 is not None or day not in by_day):
            by_day[day]={'day':day,'p':value,'source':verified_98['source'] if verified_98 else '第三方参考','url':verified_98['url'] if verified_98 else ''}
    obs=[by_day[d] for d in sorted(by_day)][-180:]
    windows=[]
    if forecast:windows=[forecast['window']]
    windows=sorted(set(windows+['2026-10-29','2026-11-12','2026-11-26','2026-12-10','2026-12-24']))
    feed={'schema':5,'region':'福建宁德','generated_at':now.isoformat(timespec='seconds'),
          'history':[history[k] for k in sorted(history)],'latest_official_day':max(history),
          'official_index':INDEXES[0],'current':current,'forecast':forecast,'windows':windows,
          'obs98':obs,'health':{**health,'api98_ok':verified_98 is not None,
                 'api98_source':verified_98['source'] if verified_98 else None,
                 'api_ok':current is not None and current.get('asof')==now.date().isoformat(),
                 'api_latest_asof':current.get('asof') if current else None}}
    def fingerprint(obj):
        return {k:v for k,v in obj.items() if k!='generated_at' and k!='health'}
    try:elapsed=(now-dt.datetime.fromisoformat(old['generated_at'])).total_seconds()
    except (ValueError,TypeError,KeyError):elapsed=999999
    same=fingerprint(old)==fingerprint(feed)
    if same and elapsed<6*3600:
        print('检查成功，数据无变化，距离上次公开心跳不足6小时，跳过发布。')
        return False
    OUT.write_text(json.dumps(feed,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('发布成功：官方',len(history),'条；新增核验',health['verified_count'],'；第三方观测日期',current.get('asof') if current else '无')
    return True

if __name__=='__main__':
    try:run()
    except Exception as exc:
        print('同步失败，旧数据保留：',exc,file=sys.stderr)
        sys.exit(1)
