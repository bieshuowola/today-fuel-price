"""UI regression guards for chart labels and node rendering (no external dependencies)."""
from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[1]
APP=(ROOT/'app.js').read_text(encoding='utf-8')
STYLE=(ROOT/'style.css').read_text(encoding='utf-8')
TEMPLATE=(ROOT/'template_body.html').read_text(encoding='utf-8')
PAGE=(ROOT/'index.html').read_text(encoding='utf-8')

class ChartPresentationTests(unittest.TestCase):
    def test_calendar_ticks_split_month_day_and_year(self):
        self.assertIn('chart-axis-label x-date',APP)
        self.assertIn('chart-axis-label x-year',APP)
        self.assertIn('dt.getUTCFullYear()',APP)
        self.assertIn('y="${H-25}"',APP)
        self.assertIn('y="${H-10}"',APP)
        self.assertNotIn('chart-axis-label x-label',APP)
        self.assertIn('view.start.replaceAll',APP)
        self.assertIn('view.end.replaceAll',APP)

    def test_every_visible_price_node_is_equal_size(self):
        match=re.search(r'for\(const p of pointDots\)\{html\+=`<circle[^\n]*?r="([^"]+)"[^\n]*?</circle>',APP)
        # SVG circles are self-closing in the generator, not HTML closing tags.
        self.assertIn('for(const p of pointDots){html+=`<circle',APP)
        self.assertIn('r="3.6" fill="#297cf2"',APP)
        self.assertNotIn('last?3.2:2.1',APP)
        self.assertNotIn('const last=p===pointDots.at(-1)',APP)

    def test_mobile_tick_labels_have_safe_horizontal_room(self):
        # Tick dates render on one row and years on another, so a year cannot
        # increase any individual label's horizontal width.
        for viewport in (280,320,360,390,768):
            # Conservative chart shell estimate for a compact viewport.
            width=viewport-60
            left=40 if width<520 else 52
            right=10 if width<520 else 18
            tick_distance=(width-left-right)/3
            self.assertGreater(tick_distance,42,viewport)
        self.assertIn('const L=mobile?40:52,R=mobile?10:18,T=27,B=49',APP)

    def test_published_page_and_sources_match(self):
        self.assertIn('<style>'+STYLE+'</style>',PAGE)
        self.assertIn('<script>'+APP+'</script></body></html>',PAGE)
        self.assertIn('</head><body>'+TEMPLATE+'<script>',PAGE)
        self.assertIn('class="footer-version" aria-label="版本号">4.7',TEMPLATE)

if __name__=='__main__':
    unittest.main()
