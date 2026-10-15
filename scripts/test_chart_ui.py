"""Regression checks for a clean selectable oil-price chart and year-segmented axis."""
from pathlib import Path
import re
import subprocess
import unittest

ROOT=Path(__file__).resolve().parents[1]
APP=(ROOT/'app.js').read_text(encoding='utf-8')
STYLE=(ROOT/'style.css').read_text(encoding='utf-8')
BODY=(ROOT/'template_body.html').read_text(encoding='utf-8')
PAGE=(ROOT/'index.html').read_text(encoding='utf-8')

class ChartPresentationTests(unittest.TestCase):
    def test_no_always_visible_chart_points(self):
        chart=APP.split('function renderChart(view){',1)[1].split('function render(){',1)[0]
        self.assertNotIn('for(const p of pointDots)',chart)
        self.assertNotIn('const pointDots=',chart)
        self.assertIn('id="crossDot"',chart)
        self.assertIn('r="5" fill="#297cf2"',chart)
        self.assertIn('fill="url(#fuelAreaGradient)"',chart)

    def test_years_are_axis_spans_not_repeated_dates(self):
        helper=APP.split('function chartTimeAxis(',1)[1].split('function renderChart(view){',1)[0]
        self.assertIn('text-anchor="middle"',helper)
        self.assertIn('chart-axis-label x-year-band',helper)
        self.assertIn('chart-year-rule',helper)
        self.assertIn('chart-axis-label x-date',helper)
        self.assertIn('if(crossYear)',helper)
        self.assertNotIn('chart-axis-label x-year"',helper)
        self.assertIn('view.start.replaceAll',APP)
        self.assertIn('view.end.replaceAll',APP)

    def test_interaction_and_dismissal(self):
        self.assertIn("selectable=dots.filter(p=>!p.baseline&&!p.carried)",APP)
        self.assertIn('shell.onpointerdown=e=>',APP)
        self.assertIn('shell.onpointermove=e=>',APP)
        self.assertIn('shell.chartClearSelection=hideSelection',APP)
        self.assertIn('document.addEventListener(\'pointerdown\'',APP)
        self.assertIn("e.key==='Escape'",APP)
        self.assertIn("e.key==='ArrowRight'",APP)
        self.assertIn('tabindex="0"',BODY)

    def test_year_band_has_enough_plot_space(self):
        self.assertIn('B=crossYear?63:43',APP)
        self.assertIn('inset=Math.min(23,plotWidth/8)',APP)
        self.assertIn('const middle=Math.max(left+13',APP)
        self.assertIn('if(x2-x1>=18)',APP)
        self.assertIn("const crossYear=view.start.slice(0,4)!==view.end.slice(0,4)",APP)

    def test_real_axis_function_across_mobile_widths(self):
        # Execute the actual browser axis helper in Node, instead of trusting string matches.
        helper=APP.split('function chartTimeAxis(',1)[1].split('function renderChart(view){',1)[0]
        helper='function chartTimeAxis('+helper
        node=r'''
const assert=require('node:assert/strict');
const millis=s=>Date.parse(s+'T00:00:00+08:00');
const two=n=>String(n).padStart(2,'0');
//CHART_AXIS_FUNCTION
const scenarios=[
 ['2026-04-16','2026-10-16',[]],
 ['2025-10-16','2026-10-16',['2025','2026']],
 ['2024-10-16','2026-10-16',['2024','2025','2026']]
];
for(const width of [240,260,280,300,320,360,390,480,768]){
 const L=width<520?40:52,R=width<520?10:18;
 for(const [start,end,years] of scenarios){
  const svg=chartTimeAxis(start,end,L,width-R,262);
  const ds=[...svg.matchAll(/<text class="chart-axis-label x-date" x="([^"]+)"/g)].map(m=>+m[1]);
  assert.equal(ds.length,4);
  assert(ds.every(x=>x>L&&x<width-R));
  assert(ds.every((x,i)=>i===0||x-ds[i-1]>=32));
  const ys=[...svg.matchAll(/<text class="chart-axis-label x-year-band" x="([^"]+)"[^>]*>(\d{4})<\/text>/g)];
  assert.deepEqual(ys.map(m=>m[2]),years);
  assert(ys.every(m=>+m[1]>=L+12&&+m[1]<=width-R-12));
  assert(ys.every((m,i)=>i===0||+m[1]-+ys[i-1][1]>=25));
 }
}
'''
        node=node.replace('//CHART_AXIS_FUNCTION',helper)
        subprocess.run(['node','-e',node],check=True,capture_output=True,text=True)

    def test_embedded_sources_and_version(self):
        self.assertIn('<style>'+STYLE+'</style>',PAGE)
        self.assertIn('<script>'+APP+'</script></body></html>',PAGE)
        self.assertIn('</head><body>'+BODY+'<script>',PAGE)
        self.assertIn('class="footer-version" aria-label="版本号">4.8',BODY)
        subprocess.run(['node','--check',str(ROOT/'app.js')],check=True)

if __name__=='__main__':unittest.main()
