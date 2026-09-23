"""Dependency-free bilingual static documentation builder and structural checks."""
from pathlib import Path
from html import escape
from html.parser import HTMLParser
import argparse
import json
import re
import shutil

ROOT = Path(__file__).resolve().parent
LANGS = ('zh', 'en')

def load_pages():
    return json.loads((ROOT / 'content/pages.json').read_text())

def render(page_id='overview', lang='zh'):
    pages = load_pages()
    i = LANGS.index(lang)
    page = next(p for p in pages if p['id'] == page_id)
    title = 'Ops Agent 中文文档' if i == 0 else 'Ops Agent Document'
    groups = list(dict.fromkeys(p['group'][i] for p in pages))
    nav = ''
    for group in groups:
        nav += f'<details class="group" open><summary>{escape(group)}</summary>'
        for p in pages:
            if p['group'][i] != group:
                continue
            active = p['id'] == page_id
            nav += f'<details class="page-nav" {"open" if active else ""}><summary><a {"aria-current=page" if active else ""} href="/{lang}/{p["id"]}.html">{escape(p["title"][i])}</a></summary><ul>'
            nav += ''.join(f'<li><a href="/{lang}/{p["id"]}.html#{s["id"]}">{escape(s["title"][i])}</a></li>' for s in p['sections'])
            nav += '</ul></details>'
        nav += '</details>'
    sections = ''.join(f'<section id="{s["id"]}"><h2>{escape(s["title"][i])}<a class="anchor" href="#{s["id"]}" aria-label="Anchor">#</a></h2>{s["body"][i]}</section>' for s in page['sections'])
    idx = pages.index(page)
    adjacent = ''
    for target, label in ((idx-1, '上一页' if i == 0 else 'Previous'), (idx+1, '下一页' if i == 0 else 'Next')):
        if 0 <= target < len(pages):
            p = pages[target]
            adjacent += f'<a href="/{lang}/{p["id"]}.html"><small>{label}</small>{escape(p["title"][i])} →</a>'
    placeholder = '搜索文档…' if i == 0 else 'Search documentation…'
    return f'''<!doctype html>
<html lang="{lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(page['title'][i])} · {title}</title><meta name="description" content="{escape(page['intro'][i])}"><link rel="stylesheet" href="/assets/style.css"><script src="/assets/app.js" defer></script></head>
<body><a class="skip" href="#main">{'跳至正文' if i==0 else 'Skip to content'}</a><header><button id="menu" aria-label="{'切换导航' if i==0 else 'Toggle navigation'}" aria-expanded="false" aria-controls="sidebar">☰</button><a class="brand" href="/{lang}/overview.html"><span class="mark">OA</span>{title}</a><a class="language" hreflang="{LANGS[1-i]}" href="/{LANGS[1-i]}/{page_id}.html">{'English' if i==0 else '中文'}</a></header>
<aside id="sidebar"><div class="search"><label for="search">{'查找内容' if i==0 else 'Find a topic'}</label><input id="search" type="search" placeholder="{placeholder}" autocomplete="off"><div id="results" aria-live="polite"></div></div><nav aria-label="{'文档目录' if i==0 else 'Documentation'}">{nav}</nav><p class="sidebar-note">Ops Agent · {'文档' if i==0 else 'Document'}<br>{'操作指南 / API / 部署' if i==0 else 'Guides / API / Deployment'}</p></aside>
<main id="main"><div class="eyebrow">{escape(page['group'][i])}</div><h1>{escape(page['title'][i])}</h1><p class="intro">{escape(page['intro'][i])}</p><div class="section-links">{''.join(f'<a href="#{s["id"]}">{escape(s["title"][i])}</a>' for s in page['sections'])}</div>{sections}<div class="pagination">{adjacent}</div><footer>{'内容依据当前实现整理；实际操作以目标环境验证为准。' if i==0 else 'Based on the current implementation. Verify operations in your target environment.'}</footer></main></body></html>'''

def resources():
    assets = {f'/assets/{p.name}': p.read_bytes() for p in (ROOT/'assets').iterdir() if p.is_file()}
    vendor = ROOT/'node_modules/swagger-ui-dist'
    for name in ('swagger-ui.css', 'swagger-ui-bundle.js'):
        assets['/assets/'+name] = (vendor/name).read_bytes()
    assets['/swagger.html'] = (ROOT/'swagger.html').read_bytes()
    pages = load_pages()
    search = {lang: [dict(id=p['id'], title=p['title'][i], text=re.sub('<[^>]+>', ' ', p['intro'][i]+' '+' '.join(s['title'][i]+' '+s['body'][i] for s in p['sections']))) for p in pages] for i,lang in enumerate(LANGS)}
    assets['/assets/search.json'] = json.dumps(search,ensure_ascii=False).encode()
    return assets

def build():
    output = resources()
    for lang in LANGS:
        for page in load_pages():
            output[f'/{lang}/{page["id"]}.html'] = render(page['id'],lang).encode()
    output['/index.html'] = render().encode()
    return output

class Links(HTMLParser):
    def __init__(self):
        super().__init__(); self.links=[]; self.ids=[]
    def handle_starttag(self, tag, attrs):
        attrs=dict(attrs)
        if 'id' in attrs: self.ids.append(attrs['id'])
        for key in ('href','src'):
            if key in attrs: self.links.append(attrs[key])

def check(output):
    pages=load_pages()
    assert len({p['id'] for p in pages})==len(pages)
    for p in pages:
        for field in ('title','intro','group'): assert len(p[field])==2 and all(p[field])
        for s in p['sections']:
            assert len(s['title'])==len(s['body'])==2
            assert not re.search(r'https?://|src/app/|web/src/|```mermaid', ' '.join(s['body']))
    for path,data in output.items():
        if not path.endswith('.html'): continue
        doc=Links(); doc.feed(data.decode()); assert len(doc.ids)==len(set(doc.ids)), path
        for link in doc.links:
            base,_,anchor=link.partition('#'); target=base or path
            assert target in output, (path,link)
            if anchor:
                parsed=Links(); parsed.feed(output[target].decode()); assert anchor in parsed.ids,(path,link)
    spec=json.loads(output['/assets/openapi.json'])
    def refs(value):
        if isinstance(value,dict):
            if '$ref' in value:
                assert value['$ref'].startswith('#/')
                node=spec
                for key in value['$ref'][2:].split('/'): node=node[key]
            for child in value.values(): refs(child)
        elif isinstance(value,list):
            for child in value: refs(child)
    refs(spec)
    assert spec['paths']['/api/console/run']['post']['requestBody']
    assert 'text/event-stream' in spec['paths']['/api/console/run']['post']['responses']['200']['content']
    print(f'Validated {len(pages)*2} localized pages, all local links/anchors, bilingual content and OpenAPI references.')

if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--check',action='store_true'); args=parser.parse_args()
    output=build(); check(output)
    if not args.check:
        dest=ROOT/'dist'
        if dest.exists(): shutil.rmtree(dest)
        for path,data in output.items():
            target=dest/path.lstrip('/'); target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes(data)
        print(f'Built {len(output)} static resources.')
