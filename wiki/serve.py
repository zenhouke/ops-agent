"""Serve only built documentation resources; refresh mounted content without a restart."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import json
import mimetypes
from threading import Lock
from urllib.parse import urlsplit
from build import ROOT, build

lock=Lock()
cache={}
version=''
def refresh():
    global cache,version
    files=[ROOT/'build.py',ROOT/'swagger.html',*sorted((ROOT/'content').glob('*')),*sorted((ROOT/'assets').glob('*'))]
    stamp=hashlib.sha256(repr([(str(p),p.stat().st_mtime_ns,p.stat().st_size) for p in files]).encode()).hexdigest()
    with lock:
        if stamp!=version:
            cache=build(); version=stamp
        return cache,version

class Handler(BaseHTTPRequestHandler):
    def do_HEAD(self): self.do_GET(head=True)
    def do_GET(self,head=False):
        path=urlsplit(self.path).path
        try:
            content,stamp=refresh()
            if path=='/__version': data=json.dumps({'version':stamp}).encode(); kind='application/json'
            else:
                if path=='/': path='/index.html'
                if path not in content: self.send_error(404); return
                data=content[path]; kind=mimetypes.guess_type(path)[0] or 'application/octet-stream'
            self.send_response(200)
            self.send_header('Content-Type',kind+('; charset=utf-8' if kind.startswith('text/') else ''))
            self.send_header('Content-Length',str(len(data)))
            self.send_header('Cache-Control','no-cache')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Referrer-Policy','no-referrer')
            self.end_headers()
            if not head: self.wfile.write(data)
        except Exception:
            self.send_error(500,'Documentation build failed; check content and dependencies')

if __name__=='__main__':
    refresh()
    print('Documentation listening on 0.0.0.0:33003',flush=True)
    ThreadingHTTPServer(('0.0.0.0',33003),Handler).serve_forever()
