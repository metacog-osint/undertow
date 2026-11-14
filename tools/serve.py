"""Serve a built Undertow site locally with the headers from its _headers file (Cloudflare Pages format), CSP
included, so a local check sees what the live site enforces. Copied from Headwind (adapted from Blackout).

    python tools/serve.py [port] [--dir FOLDER]   (default port 8781, folder site/)
"""
import argparse
import http.server
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent


def rules(site: pathlib.Path):
    out, current = [], None
    for line in (site / "_headers").read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line[0].isspace():
            current = (re.compile("^" + re.escape(line.strip()).replace(r"\*", ".*") + "$"), [])
            out.append(current)
        elif current:
            k, _, v = line.strip().partition(":")
            current[1].append((k.strip(), v.strip()))
    return out


def handler(site: pathlib.Path):
    class Handler(http.server.SimpleHTTPRequestHandler):
        extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map,
                          ".mjs": "text/javascript", ".js": "text/javascript", ".geojson": "application/geo+json"}

        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(site), **kw)

        def end_headers(self):
            path = self.path.split("?", 1)[0]
            for rx, headers in rules(site):
                if rx.match(path):
                    for k, v in headers:
                        if k.lower() != "strict-transport-security":  # not over plain http
                            self.send_header(k, v)
            super().end_headers()
    return Handler


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("port", nargs="?", type=int, default=8781)
    ap.add_argument("--dir", default=str(ROOT / "site"))
    a = ap.parse_args()
    site = pathlib.Path(a.dir).resolve()
    print(f"Serving {site} on http://127.0.0.1:{a.port} with its _headers", flush=True)
    http.server.ThreadingHTTPServer(("127.0.0.1", a.port), handler(site)).serve_forever()
