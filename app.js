(()=>{'use strict';
const $=id=>document.getElementById(id), G=['92','95','98'], NOW_WINDOW=['2026-10-29','2026-11-12','2026-11-26','2026-12-10','2026-12-24'];
const BASE=window.FUEL_OFFICIAL||[];const CACHE_KEY='fuel_price_dashboard_4_2';const LEGACY_CACHE_KEY='fuel_price_dashboard_4';
const state={grade:'95',period:365,history:BASE,live:null,liveOnline:false,liveSource:'',feedOnline:false,feedAt:null,feedFresh:false,feedSeen:false,forecast:null,windows:NOW_WINDOW,obs98:[],loading:false,lastCheck:0,status:'',feedURL:window.FUEL_FEED_URL||'',hoverIndex:null};
const two=x=>String(x).padStart(2,'0'),cash=n=>Number(n).toFixed(2);
const bjt=()=>new Date(new Date().toLocaleString('en-US',{timeZone:'Asia/Shanghai'}));
const dayOf=d=>`${d.getFullYear()}-${two(d.getMonth()+1)}-${two(d.getDate())}`,today=()=>dayOf(bjt());
const fmtDay=s=>s?`${+s.slice(5,7)} 月 ${+s.slice(8,10)} 日`:'日期未核实';
const fmtRangeDay=(s,duration)=>duration>=365?`${s.slice(0,4)}年${+s.slice(5,7)}月${+s.slice(8,10)}日`:fmtDay(s);
const millis=s=>Date.parse(s+'T00:00:00+08:00');
const isDay=s=>typeof s==='string'&&/^20\d{2}-\d\d-\d\d$/.test(s)&&!Number.isNaN(millis(s));
const addDays=(date,delta)=>{const d=new Date(millis(date)+(delta*864e5));return new Date(d.getTime()+8*36e5).toISOString().slice(0,10)};
const rangeStart=(days)=>{const d=bjt();if(days===90)d.setMonth(d.getMonth()-3);else if(days===180)d.setMonth(d.getMonth()-6);else if(days===365)d.setFullYear(d.getFullYear()-1);else d.setFullYear(d.getFullYear()-2);return dayOf(d)};
const priceValid=p=>p&&Number(p['92'])>4&&Number(p['92'])<18&&Number(p['95'])>Number(p['92'])&&Number(p['95'])<22;
const URL_OK=url=>typeof url==='string'&&/^https:\/\//i.test(url)&&url.length<800;
function cleanRows(rows){if(!Array.isArray(rows))return[];const valid=[];for(const r of rows){if(!r||!isDay(r.day)||r.day>today()||r.source!=='official'||!priceValid(r.p)||!URL_OK(r.url)||!/^(fgw\.(fj|fujian)\.gov\.cn)$/.test(new URL(r.url).hostname))continue;valid.push({day:r.day,p:{'92':+r.p['92'],'95':+r.p['95']},url:r.url,source:'official'});}return [...new Map(valid.map(r=>[r.day,r])).values()].sort((a,b)=>a.day.localeCompare(b.day));}
function persist(){try{localStorage.setItem(CACHE_KEY,JSON.stringify({grade:state.grade,period:state.period,feedURL:state.feedURL,history:state.history,live:state.live,forecast:state.forecast,obs98:state.obs98}))}catch{}}
try{let saved=JSON.parse(localStorage.getItem(CACHE_KEY)||localStorage.getItem(LEGACY_CACHE_KEY)||'{}');if(G.includes(saved.grade))state.grade=saved.grade;if([90,180,365,730].includes(+saved.period))state.period=+saved.period;if(URL_OK(saved.feedURL))state.feedURL=saved.feedURL;if(Array.isArray(saved.obs98))state.obs98=saved.obs98.filter(r=>isDay(r.day)&&r.day<=today()&&Number(r.p)>5&&Number(r.p)<27).slice(-160);const old=cleanRows(saved.history);if(old.length){state.history=mergeOfficial(BASE,old);}if(verifyObservation(saved.live,false))state.live=saved.live;}catch{}
function mergeOfficial(...inputs){const map=new Map();for(const arr of inputs)for(const r of cleanRows(arr))map.set(r.day,r);return [...map.values()].sort((a,b)=>a.day.localeCompare(b.day));}
// The row day is the official ANOUNCEMENT date at 24:00; new price is effective the next day.
function confirmed(){const d=today();return state.history.filter(x=>x.day<d);}
function lastOfficial(){return confirmed().at(-1)||null;}
function lastConfirmedPrice(){return lastOfficial()?.p||null;}
function verifyObservation(obj,needFresh=true){if(!obj||!priceValid(obj.p)||!isDay(obj.asof)||obj.asof>today())return false;const age=(millis(today())-millis(obj.asof))/864e5;return age<=(needFresh?3:7);}
function acceptLive(next){if(!verifyObservation(next))return false;if(state.live&&verifyObservation(state.live)&&next.asof<state.live.asof)return false;if(state.feedOnline&&state.live?.ref98&&!next.ref98)return false;state.live=next;state.liveOnline=true;state.liveSource=next.source||'第三方数据';if(Number(next.p?.['98'])>5&&Number(next.p['98'])<27){const previous=state.obs98.at(-1);if((!previous||next.asof>previous.day)&&(!previous||Math.abs(previous.p-Number(next.p['98']))>=.005))state.obs98.push({day:next.asof,p:Number(next.p['98'])});state.obs98=state.obs98.slice(-160);}return true;}
function afterOfficialLive(){if(!verifyObservation(state.live))return null;const ref=lastOfficial();if(!ref)return null;
 // 已验证的官方最高零售限价优先于任何相互矛盾的第三方报价。
 if(state.feedOnline)return null;
 // 当日新公告在 24:00 才生效，禁止 API 抢先把明日价格当成今日价格。
 if(state.history.some(x=>x.day===today()))return null;
 if(state.live.asof<=ref.day)return null;
 // 刚生效的官方价格不能因为第三方数据源不同而立即被推翻。
 if(millis(today())-millis(ref.day)<7*864e5)return null;
 const v=state.live.p;
 if(Math.abs(v['92']-ref.p['92'])<.005&&Math.abs(v['95']-ref.p['95'])<.005)return null;
 // 在官方数据源暂未完成本轮核验时，显示临时观察价并明确标注。
 return {...state.live,p:{...v},observed:true,source:'observed'};
}
function currentPrice(){const ref=lastOfficial();const observed=afterOfficialLive();const official=ref?.p?.[state.grade];const api=(state.live&&verifyObservation(state.live)&&state.live.p?.[state.grade]!=null)?+state.live.p[state.grade]:null;
 if(state.grade==='98'){
   if(api!=null)return {n:api,kind:'third-party',asof:state.live.asof};
   return {n:null,kind:'unknown',asof:null};
 }
 if(observed)return {n:observed.p[state.grade],kind:'observed',asof:observed.asof};
 return {n:official??null,kind:'official',asof:ref?.day||null};
}
function ledger(grade){if(grade==='98')return state.obs98.map(r=>({day:r.day,publish:r.day,p:r.p,kind:'observed',url:r.url||null})).sort((a,b)=>a.day.localeCompare(b.day));const source=confirmed().filter(r=>r.p[grade]!=null).map(r=>({day:addDays(r.day,1),publish:r.day,p:+r.p[grade],kind:'official',url:r.url}));
 const obs=afterOfficialLive();if(obs&&obs.p[grade]!=null){const v=+obs.p[grade];if(!source.length||Math.abs(v-source.at(-1).p)>.005){const day=obs.asof>source.at(-1)?.day?obs.asof:today();if(source.at(-1)?.day===day)source[source.length-1]={day,publish:obs.asof,p:v,kind:'observed'};else source.push({day,publish:obs.asof,p:v,kind:'observed'});}}
 return source.sort((a,b)=>a.day.localeCompare(b.day));}
function changes(rows){const out=[];for(let i=1;i<rows.length;i++){let d=+(rows[i].p-rows[i-1].p).toFixed(2);if(Math.abs(d)>=.005)out.push({...rows[i],delta:d});}return out;}
function periodEntries(grade,days){const all=ledger(grade),start=rangeStart(days),end=today();const left=[...all].reverse().find(x=>x.day<=start),right=all.filter(x=>x.day>start&&x.day<=end),initial=left?{...left,day:start,baseline:true}:null;const points=[...(initial?[initial]:[]),...right];if(points.length&&points.at(-1).day<end)points.push({...points.at(-1),day:end,carried:true,kind:points.at(-1).kind});
 const stale=(lastOfficial()&&millis(today())-millis(addDays(lastOfficial().day,1))>28*864e5&&!verifyObservation(state.live)&&!state.feedOnline);
 const uncertain=!!afterOfficialLive();const lastGood=all.at(-1)?.day||null;
 const coverage=Boolean(initial)&&!stale;
 return {all,start,end,points,coverage,stale,uncertain,lastGood};}
function latestChange(grade){return changes(ledger(grade)).at(-1)||null;}
function renderHeader(){const p=currentPrice();$('price').textContent=p.n==null?'—':cash(p.n);$('priceLabel').textContent=`${state.grade} 号汽油 · ${state.grade==='98'?'第三方参考价':'福建最高零售限价'} · 元/升`;
 const found=latestChange(state.grade),delta=$('delta'),ctx=$('deltaContext');delta.className='change';if(found){delta.textContent=`${found.delta>0?'↑ +':'↓ −'}${cash(Math.abs(found.delta))}`;delta.classList.add(found.delta>0?'up':'down');ctx.textContent=`最近价格变动 · ${fmtDay(found.publish)}${state.grade==='98'?'（第三方参考）':found.kind==='observed'?'（待官方核验）':''}`;}else{delta.textContent='暂无可核实变化';ctx.textContent=state.grade==='98'?'不提供未经核实的涨跌幅':'历史信息不足';}
 $('priceKind').textContent=p.kind==='official'?'官方公告价':p.kind==='observed'?'接口观察价 · 待核验':p.kind==='third-party'?(state.live?.ref98?`98号第三方参考 · ${state.live.ref98.source} · 数据${fmtDay(state.live.ref98.price_date)}`:'第三方实时参考价'):'当前无可核实报价';$('priceKind').hidden=p.kind==='official';
 document.querySelectorAll('[data-grade]').forEach(el=>{const y=el.dataset.grade===state.grade;el.classList.toggle('active',y);el.setAttribute('aria-pressed',String(y))});document.querySelectorAll('[data-period]').forEach(el=>{const y=+el.dataset.period===state.period;el.classList.toggle('active',y);el.setAttribute('aria-pressed',String(y))});
 const ref=lastOfficial();let info='仅有内置历史快照 · 未接入在线同步';if(state.feedOnline)info=`官方历史已核对 · ${state.feedAt||'检查时间未知'}`;else if(state.feedSeen)info='官方历史同步过期或异常 · 数据可能滞后';else if(state.liveOnline)info=`仅第三方报价已获取 · ${state.live?.asof||'日期未知'}`;else if(state.status)info=state.status;
 const infoSep=info.lastIndexOf(' · ');$('statusText').textContent=infoSep<0?info:info.slice(0,infoSep);$('statusTime').textContent=infoSep<0?'':info.slice(infoSep+3);$('statusTime').hidden=infoSep<0;
 const currentStale=ref&&millis(today())-millis(ref.day)>28*864e5&&!verifyObservation(state.live)&&!state.feedOnline;
 $('status').className='status '+(state.feedOnline?'good':currentStale?'bad':'warn');
 $('asof').textContent=ref?fmtDay(ref.day):'暂无官方历史';
 $('mainHeading').textContent=currentStale?'历史参考油价':'当前油价';}
function renderCalendar(){const now=new Date();const valid=state.windows.filter(x=>isDay(x)&&millis(addDays(x,1))>now.getTime()).sort();const next=valid[0]||null;
 if(!next){$('nextDate').textContent='等待公布';$('countdown').textContent='暂无日期';$('nextText').textContent='调价日历待更新';return;}
 $('nextDate').textContent=`${fmtDay(next)} 24:00`;$('nextText').textContent='北京时间 · 调价日历参考';
 const sec=Math.max(0,Math.floor((millis(addDays(next,1))-now.getTime())/1000)),d=Math.floor(sec/86400),h=Math.floor(sec%86400/3600),m=Math.floor(sec%3600/60);
 $('countdown').textContent=`${d}天 ${h}小时 ${two(m)}分`;
}
function renderForecast(){const el=$('forecast'),f=state.forecast,valid=f&&isDay(f.window)&&isDay(f.asof)&&state.windows.includes(f.window)&&f.window===state.windows.find(w=>millis(addDays(w,1))>Date.now())&&millis(today())-millis(f.asof)<=3*864e5&&f.asof<=today();
 $('forecastLink').hidden=true;el.className='';
 if(!valid){el.textContent='暂无可靠的新预测';$('forecastNote').textContent='第三方预测仅供参考';return;}
 const m={'上调':'可能上涨','下调':'可能下降','搁浅':'可能持平','不调':'可能持平'};if(!m[f.direction]){el.textContent='暂无可靠的新预测';return;}
 el.textContent=m[f.direction];el.className=f.direction==='上调'?'up':f.direction==='下调'?'down':'';
 $('forecastNote').textContent=Array.isArray(f.range)?`估计 ${f.range.map(cash).join('–')} 元/升 · ${f.asof}`:`${f.asof} · 非官方结果`;
 if(URL_OK(f.url)){$('forecastLink').href=f.url;$('forecastLink').hidden=false;}
}
function renderRecent(){const subset=changes(ledger(state.grade)).slice(-6).reverse(),box=$('records');box.replaceChildren();$('recentSubtitle').textContent='最近 6 次实际价格变化 · 排除持平窗口';if(state.grade==='98'){$('recentSubtitle').textContent='第三方已记录价格变化 · 非官方调价日';if(!subset.length){box.append(make('div','empty','尚未累计足够的第三方 98 号价格变动记录。'));return;}}
 if(!subset.length){box.append(make('div','empty','暂无已记录的实际价格变化'));return;}
 for(const row of subset){const outer=make('div','history-row'),left=make('div',''),date=make('div','history-day',fmtDay(row.publish||row.day)),caption=make('div','history-sub',state.grade==='98'?'第三方参考报价':row.kind==='observed'?'接口观察价 · 非官方调价日':'官方生效价格'),right=make('div','history-value'),cost=make('b','',`¥${cash(row.p)}`),movement=make('em',row.delta>0?'up':'down',`${row.delta>0?'+':'−'}${cash(Math.abs(row.delta))}`);left.append(date,caption);right.append(cost,movement);outer.append(left,right);box.append(outer);}}
function make(tag,cls,txt){const el=document.createElement(tag);if(cls)el.className=cls;if(txt!=null)el.textContent=txt;return el;}
function renderStats(view){let title=({'90':'近 3 个月','180':'近半年','365':'近 1 年','730':'近 2 年'})[state.period];$('statsTitle').textContent=title+(state.grade==='98'?'第三方参考统计 · 仅已记录区间':'价格统计');document.querySelectorAll('[data-stats-period]').forEach(x=>x.textContent=title.replace('近 ','近'));
 const pts=view.points.filter(x=>Number.isFinite(x.p));const recorded=pts.filter(x=>!x.carried&&!x.baseline);const enough=state.grade==='98'?recorded.length>=2:view.coverage;if(!enough||!pts.length){for(const id of ['statMin','statMax','statDistance'])$(id).textContent='—';$('minAt').textContent=state.grade==='98'?'已记录样本不足':'该周期数据未完整核验';$('maxAt').textContent='不计算不可靠极值';$('distanceNote').textContent=view.stale?'官方记录需要更新':'等待完整官方记录';return;}
 const mn=Math.min(...pts.map(x=>x.p)),mx=Math.max(...pts.map(x=>x.p));const low=pts.find(x=>Math.abs(x.p-mn)<.005),high=pts.find(x=>Math.abs(x.p-mx)<.005);const current=currentPrice().n;
 $('statMin').textContent='¥'+cash(mn);$('statMax').textContent='¥'+cash(mx);$('statDistance').textContent=current==null?'—':`${current-mn>=0?'+':'−'}${cash(Math.abs(current-mn))}`;
 $('minAt').textContent=fmtDay(low.day)+(low.baseline?'（期初在售）':' 起');$('maxAt').textContent=fmtDay(high.day)+(high.baseline?'（期初在售）':' 起');$('distanceNote').textContent=state.grade==='98'?'第三方样本 · 非官方价格':view.uncertain?'含第三方观察 · 暂定统计':'较周期最低价';}
function monotonePath(dots){if(!dots.length)return '';if(dots.length===1)return `M ${dots[0].x} ${dots[0].y}`;
 const n=dots.length,ds=[],slopes=[];for(let i=0;i<n-1;i++)ds.push((dots[i+1].y-dots[i].y)/(dots[i+1].x-dots[i].x));
 for(let i=0;i<n;i++){if(i===0)slopes[i]=ds[0];else if(i===n-1)slopes[i]=ds[n-2];else if(ds[i-1]*ds[i]<=0)slopes[i]=0;else slopes[i]=2/(1/ds[i-1]+1/ds[i]);}
 let path=`M ${dots[0].x.toFixed(2)} ${dots[0].y.toFixed(2)}`;
 for(let i=0;i<n-1;i++){const a=dots[i],b=dots[i+1],dx=b.x-a.x;path+=` C ${(a.x+dx/3).toFixed(2)} ${(a.y+slopes[i]*dx/3).toFixed(2)}, ${(b.x-dx/3).toFixed(2)} ${(b.y-slopes[i+1]*dx/3).toFixed(2)}, ${b.x.toFixed(2)} ${b.y.toFixed(2)}`;}
 return path;}
function renderChart(view){$('legendText').textContent=state.grade+' 号汽油';$('coverage').textContent=state.grade==='98'?(view.all.length>=2?`第三方记录 · ${fmtDay(view.all[0].day)}—${fmtDay(view.all.at(-1).day)} · 非完整周期`:'98 号历史样本积累中'):view.stale?'部分数据可能过期 · 等待同步':view.uncertain?'含待核实观察节点 · 统计仅供参考':`日期范围 · ${fmtRangeDay(view.start,state.period)}—${fmtRangeDay(view.end,state.period)}`;
 const svg=$('chart'),shell=$('chartShell'),tip=$('tip'),W=shell.clientWidth||420,H=shell.clientHeight||270,mobile=W<520;tip.classList.remove('visible','below');let pts=view.points;if(pts.length<2){svg.setAttribute('viewBox',`0 0 ${W} ${H}`);svg.innerHTML=`<text x="${W/2}" y="${H/2}" text-anchor="middle" class="chart-axis-label">${state.grade==='98'?'98 号历史记录仍不足以画出趋势':'尚无足够历史记录'}</text>`;return;}
 // Draw in real CSS-pixel coordinates to keep circular markers and type undistorted.
 const L=mobile?40:52,R=mobile?10:18,T=27,B=43,ww=W-L-R,hh=H-T-B;
 const mn=Math.min(...pts.map(p=>p.p)),mx=Math.max(...pts.map(p=>p.p)),margin=Math.max(.14,(mx-mn)*.22),bottom=mn-margin,top=mx+margin;
 const x=p=>L+ww*(millis(p.day)-millis(view.start))/Math.max(1,millis(view.end)-millis(view.start));const y=v=>T+(top-v)/(top-bottom)*hh;
 const dots=pts.map(p=>({...p,x:x(p),y:y(p.p)}));const path=monotonePath(dots);
 // Vertical blue area gradient under the real-price curve. SVG gradient is inline
 // so it also works in Android's file:// viewer without external styles or scripts.
 let html=`<defs><linearGradient id="fuelAreaGradient" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#4896fa" stop-opacity=".41"/><stop offset="48%" stop-color="#6aafff" stop-opacity=".25"/><stop offset="100%" stop-color="#d6e7ff" stop-opacity=".075"/></linearGradient></defs>`;
 for(let i=0;i<4;i++){const yy=T+hh*i/3;html+=`<line x1="${L}" x2="${W-R}" y1="${yy}" y2="${yy}" stroke="#edf0f4" stroke-dasharray="3 7"/><text class="chart-axis-label" x="${L-9}" y="${yy+4}" text-anchor="end">${cash(top-(top-bottom)*i/3)}</text>`;}
 for(let i=0;i<4;i++){const t=millis(view.start)+i*(millis(view.end)-millis(view.start))/3,dt=new Date(t+8*36e5),d=`${dt.getUTCFullYear()}/${two(dt.getUTCMonth()+1)}/${two(dt.getUTCDate())}`;html+=`<text class="chart-axis-label x-label" x="${L+i*ww/3}" y="${H-12}" text-anchor="${i===0?'start':i===3?'end':'middle'}">${d}</text>`;}
 html+=`<path d="${path} L ${dots.at(-1).x.toFixed(2)} ${H-B} L ${dots[0].x.toFixed(2)} ${H-B} Z" fill="url(#fuelAreaGradient)"/><path d="${path}" fill="none" stroke="#297cf2" stroke-width="2.9" stroke-linejoin="round" stroke-linecap="round"/>`;
 const pointDots=dots.filter(d=>!d.carried&&!d.baseline);
 for(const p of pointDots){const last=p===pointDots.at(-1);html+=`<circle cx="${p.x}" cy="${p.y}" r="${last?3.2:2.1}" fill="#297cf2"/>`;}
 html+=`<line id="crossV" x1="0" x2="0" y1="${T}" y2="${H-B}" stroke="#7b8da5" stroke-width="1.3" opacity="0"/><line id="crossH" x1="${L}" x2="${W-R}" y1="0" y2="0" stroke="#c4d0dd" stroke-dasharray="4 5" opacity="0"/><circle id="crossDot" cx="0" cy="0" r="4" fill="#297cf2" stroke="white" stroke-width="1.4" opacity="0"/>`;
 svg.setAttribute('viewBox',`0 0 ${W} ${H}`);svg.setAttribute('preserveAspectRatio','xMidYMid meet');svg.innerHTML=html;svg.setAttribute('aria-label',`${state.grade}号汽油${state.period}天范围价格变化`);
 function show(i){const p=dots[i],bound=shell.getBoundingClientRect(),v=svg.querySelector('#crossV'),h=svg.querySelector('#crossH'),circle=svg.querySelector('#crossDot');v.setAttribute('x1',p.x);v.setAttribute('x2',p.x);v.setAttribute('opacity','1');h.setAttribute('y1',p.y);h.setAttribute('y2',p.y);h.setAttribute('opacity','1');circle.setAttribute('cx',p.x);circle.setAttribute('cy',p.y);circle.setAttribute('opacity','1');tip.classList.toggle('below',p.y<105);tip.style.left=`${Math.max(69,Math.min(bound.width-69,p.x/W*bound.width))}px`;tip.style.top=`${p.y<105?p.y/H*bound.height+8:p.y/H*bound.height-8}px`;$('tipDate').textContent=(p.publish||p.day).replaceAll('-','/');$('tipPrice').textContent='¥'+cash(p.p)+' / 升';$('tipNote').textContent=p.baseline?'期初在售':p.carried?'沿用上次价格':state.grade==='98'?'第三方参考价':p.kind==='observed'?'第三方观察（未核验）':'官方调整价';tip.classList.add('visible');}
 const choose=e=>{const rect=shell.getBoundingClientRect(),coord=(e.clientX-rect.left)/rect.width*W;let ix=0;dots.forEach((d,i)=>{if(Math.abs(d.x-coord)<Math.abs(dots[ix].x-coord))ix=i});show(ix)};
 shell.onpointermove=choose;shell.onpointerdown=choose;shell.onpointerleave=()=>{tip.classList.remove('visible');['crossV','crossH','crossDot'].forEach(id=>svg.querySelector('#'+id)?.setAttribute('opacity','0'));};
}
function render(){renderHeader();renderCalendar();renderForecast();renderRecent();const view=periodEntries(state.grade,state.period);renderChart(view);renderStats(view);}
function toast(msg){const n=$('toast');n.textContent=msg;n.classList.add('show');clearTimeout(toast.handle);toast.handle=setTimeout(()=>n.classList.remove('show'),3400);}
function dateFrom(value){const m=String(value||'').match(/(20\d{2})[-\/年.]\s*(\d{1,2})[-\/月.]\s*(\d{1,2})/);return m?`${m[1]}-${two(m[2])}-${two(m[3])}`:null;}
function parseNext(value){const str=String(value||''),m=str.match(/(?:(20\d{2})年)?\s*(\d{1,2})月\s*(\d{1,2})日/);if(!m)return null;let y=+(m[1]||today().slice(0,4)),mon=+m[2],d=+m[3];if(mon<1||mon>12||d<1||d>31)return null;let next=`${y}-${two(mon)}-${two(d)}`;if(m[1]==null&&millis(addDays(next,1))<Date.now())next=`${y+1}-${two(mon)}-${two(d)}`;return millis(addDays(next,1))-Date.now()<65*864e5?next:null;}
function parse60(j){if(j?.code!==200||!Array.isArray(j.data?.items))throw Error('接口格式异常');const data=j.data;if(!/(福建|宁德)/.test(data.region||''))throw Error('接口地区不是福建宁德');const p={};for(const item of data.items){const match=String(item.name||'').match(/^(92|95|98)/);if(match)p[match[1]]=Number(item.price);}const tr=data.trend||{},asof=dateFrom(data.updated),out={p,asof,region:data.region,source:'60s 油价 API'};if(!verifyObservation(out))throw Error('接口返回过期或异常报价');const window=parseNext(tr.next_adjustment_date);let forecast=null;if(window&&['上调','下调','搁浅','不调'].includes(tr.direction)){
 forecast={window,direction:tr.direction,asof,source:'60s 油价预测（第三方）',url:'https://docs.60s-api.viki.moe/376793576e0'};
 const a=Number(tr.change_liter_min),b=Number(tr.change_liter_max);if(tr.change_liter_min!=null&&tr.change_liter_max!=null&&a>=0&&a<=b&&b<2)forecast.range=[a,b];}
 return {current:out,forecast,next:window};}
function parseAlternate(j){if(j?.code!==0||!Array.isArray(j.data?.prices))throw Error('备用数据格式异常');const p={};for(const i of j.data.prices){const m=String(i.type||i.name||'').match(/(92|95|98)/);if(m)p[m[1]]=Number(i.price);}const out={p,asof:dateFrom(j.data.update_date),source:'第三方备用 API'};if(!verifyObservation(out))throw Error('备用接口过期');return{current:out,forecast:null,next:parseNext(j.data.next_adjustment)};}
async function request(url,options={}){const controller=new AbortController();const timeout=setTimeout(()=>controller.abort(),8000);try{const r=await fetch(url,{...options,signal:controller.signal,cache:'no-store',credentials:'omit'});if(!r.ok)throw Error('HTTP '+r.status);return await r.json();}finally{clearTimeout(timeout);}}
function feedValid(data){if(data?.schema!==5||!Array.isArray(data.history)||data.region!=='福建宁德'||!isDay((data.generated_at||'').slice(0,10)))throw Error('历史源格式不正确');const rows=cleanRows(data.history);if(rows.length<20)throw Error('官方历史条目太少，拒绝采用');const checked=(data.health?.checked_at||'').slice(0,10);if(checked&&isDay(checked)&&rows.some(x=>x.day>checked))throw Error('发现晚于官方核验时间的记录，拒绝采用');return rows;}
async function getFeed(){// 正式部署后，同源的最新官方历史数据无需任何用户配置。
 let url=location.protocol==='https:'?'':state.feedURL;if(!url&&location.protocol==='https:')url=new URL('./data/latest.json',location.href).href;
 if(!url)return null;
 const response=await request(url);const rows=feedValid(response);state.feedSeen=true;const old=state.history.length;
 state.history=mergeOfficial(state.history,rows);
 if(Array.isArray(response.obs98)){const bag=new Map([...state.obs98,...response.obs98].filter(r=>isDay(r.day)&&r.day<=today()&&Number(r.p)>5&&Number(r.p)<27).map(r=>[r.day,{day:r.day,p:Number(r.p),source:r.source||'第三方参考',url:r.url||null}]));state.obs98=[...bag.values()].sort((a,b)=>a.day.localeCompare(b.day)).slice(-180);}
 state.feedAt=response.health?.checked_at?.slice(0,16).replace('T',' ')||null;
 const checked=response.health?.checked_at;
 const recent=checked&&Number.isFinite(Date.parse(checked))&&Date.now()-Date.parse(checked)>=-120000&&Date.now()-Date.parse(checked)<18*3600*1000;
 const documentHealthy=response.health?.index_ok===true&&response.health?.link_count>=10;
 state.feedFresh=!!recent;
 state.feedOnline=!!recent&&documentHealthy;
 if(response.current)acceptLive(response.current);
 if(response.forecast&&isDay(response.forecast.window)&&isDay(response.forecast.asof)&&(!state.forecast||response.forecast.asof>=state.forecast.asof))state.forecast=response.forecast;
 if(Array.isArray(response.windows)){const vals=response.windows.filter(isDay).filter(x=>millis(addDays(x,1))>Date.now()-864e5);if(vals.length)state.windows=[...new Set([...state.windows,...vals])].sort();}
 return {type:'feed',added:state.history.length-old,verified:state.feedOnline};}
async function getApi(){const main=async()=>{let err;for(const region of ['福建宁德','福建']){try{return parse60(await request('https://60s.viki.moe/v2/fuel-price?region='+encodeURIComponent(region)));}catch(e){err=e;if(e.name==='AbortError'||/Failed to fetch|NetworkError/.test(e.message))break;}}throw err||Error('主 API 不可用');};
 const backup=()=>request('https://v1.apizero.cn/api/oil-price',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({province:'福建'})}).then(parseAlternate);
 const result=await Promise.any([main(),backup()]);if(result.current)acceptLive(result.current);if(result.forecast&&(!state.forecast||result.forecast.asof>=state.forecast.asof))state.forecast=result.forecast;if(result.next&&result.next>=today())state.windows=[...new Set([...state.windows,result.next])].sort();return {type:'api'};}
async function refresh(user=false){if(state.loading)return;state.loading=true;state.lastCheck=Date.now();$('refresh').disabled=true;$('refresh').classList.add('loading');state.feedOnline=false;state.feedFresh=false;state.feedSeen=false;state.liveOnline=false;state.status='正在检查官方历史与最新报价…';renderHeader();
 const results=await Promise.allSettled([getFeed(),getApi()]);let ok=results.some(r=>r.status==='fulfilled'&&r.value!=null);state.loading=false;$('refresh').disabled=false;$('refresh').classList.remove('loading');if(!ok)state.status='联网失败 · 显示本地已核验历史';else if(!state.feedOnline)state.status='未验证官方在线同步 · 仅展示历史缓存/第三方报价';persist();render();if(user)toast(state.feedOnline?'官方历史已核对，整页已同步':ok?'只获取到第三方或旧历史数据，未确认官方同步':'无法联网，已保留历史快照');}
document.querySelectorAll('[data-grade]').forEach(b=>b.addEventListener('click',()=>{state.grade=b.dataset.grade;state.hoverIndex=null;persist();render();}));document.querySelectorAll('[data-period]').forEach(b=>b.addEventListener('click',()=>{state.period=Number(b.dataset.period);persist();render();}));
$('refresh').addEventListener('click',()=>refresh(true));
window.addEventListener('resize',()=>renderChart(periodEntries(state.grade,state.period)));
document.addEventListener('visibilitychange',()=>{if(!document.hidden&&Date.now()-state.lastCheck>3*60*1000)refresh(false);});
window.addEventListener('online',()=>refresh(false));render();refresh();
let lastRenderedDay=today();
setInterval(()=>{
 if(today()!==lastRenderedDay){lastRenderedDay=today();render();} // 北京时间跨日，公告在24:00自动生效，触发全页重算。
 else{renderCalendar();renderForecast();}
 if(!document.hidden&&Date.now()-state.lastCheck>=15*60*1000)refresh(false);
},60*1000);
// E2E tests use a deliberate test-only injection, NOT enabled by default in shipped production.
})();
