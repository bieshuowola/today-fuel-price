#!/usr/bin/env python3
"""Assemble portable index.html from source files."""
import json
from pathlib import Path
R=Path(__file__).resolve().parents[1]
rows=json.loads((R/'data'/'official_history.json').read_text(encoding='utf-8'))
base=json.dumps(rows,ensure_ascii=False,separators=(',',':')).replace('</','<\\/')
head='<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="theme-color" content="#f5f6f9"><meta name="color-scheme" content="light"><meta name="description" content="福建宁德今日油价、历史价格与调价走势"><title>今日油价</title><link rel="icon" type="image/png" sizes="192x192" href="./icons/icon-192.png"><link rel="icon" type="image/svg+xml" href="./favicon.svg"><link rel="apple-touch-icon" href="./icons/icon-192.png"><link rel="manifest" href="./manifest.webmanifest"><meta name="apple-mobile-web-app-title" content="今日油价">'
styles=(R/'style.css').read_text(encoding='utf-8')
body=(R/'template_body.html').read_text(encoding='utf-8')
app=(R/'app.js').read_text(encoding='utf-8')
page=head+'<style>'+styles+'</style></head><body>'+body+'<script>window.FUEL_OFFICIAL='+base+';</script><script>'+app+'</script></body></html>\n'
(R/'index.html').write_text(page,encoding='utf-8')
print('Generated index.html')
