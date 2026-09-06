#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Render the profile stat card.

Emits assets/stats-<theme>.svg for light and dark. The hosted card services are
unreliable -- github-readme-stats answers 503 for long stretches and the
activity-graph deployment is disabled -- so the card is built here and committed
to the repository instead. No webfonts, no external refs: README images are
proxied through camo, which blocks anything the SVG tries to fetch.

Run with GITHUB_TOKEN set to avoid the 60 req/hour unauthenticated limit.
"""

import io
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime

USER = os.environ.get("STATS_USER", "Senanur-ylmz")
OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")

# Markup and styling languages drown out everything else when weighted by bytes.
IGNORED_LANGS = {"HTML", "CSS", "SCSS", "Sass", "Less", "Stylus", "EJS",
                 "Handlebars", "Pug", "Blade", "Jupyter Notebook"}

THEMES = {
    "light": dict(card="#FFFBF2", border="#F0DCB0", accent="#96601F",
                  key="#A08A64", value="#4E2C13", track="#FAF0DA"),
    "dark":  dict(card="#2A1D0F", border="#56401F", accent="#E8B84F",
                  key="#C0AA83", value="#FBEFD2", track="#3D2C15"),
}

# Pastels for the language bars, cycled in order.
BAR_COLORS = ["#E0A93F", "#C97C2A", "#E8C55F", "#A9743C", "#F0D48A", "#8A5A16"]


def api(path):
    req = urllib.request.Request(
        "https://api.github.com" + path,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "stats-svg"},
    )
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def collect():
    user = api("/users/%s" % USER)
    repos, page = [], 1
    while True:
        chunk = api("/users/%s/repos?per_page=100&page=%d" % (USER, page))
        repos.extend(chunk)
        if len(chunk) < 100:
            break
        page += 1

    own = [r for r in repos if not r["fork"]]
    langs = {}
    for r in own:
        try:
            for name, size in api("/repos/%s/languages" % r["full_name"]).items():
                if name not in IGNORED_LANGS:
                    langs[name] = langs.get(name, 0) + size
        except urllib.error.HTTPError as e:
            print("  ! skipped %s (%s)" % (r["full_name"], e.code), file=sys.stderr)

    total = sum(langs.values()) or 1
    created = datetime.strptime(user["created_at"], "%Y-%m-%dT%H:%M:%SZ")
    return dict(
        stats=[
            ("repositories", str(user["public_repos"])),
            ("stars earned", str(sum(r["stargazers_count"] for r in own))),
            ("followers", str(user["followers"])),
            ("here since", created.strftime("%B %Y")),
        ],
        langs=[(n, 100.0 * v / total)
               for n, v in sorted(langs.items(), key=lambda kv: -kv[1])[:6]],
    )


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render(data, theme):
    c = THEMES[theme]
    W, H, PAD = 860, 250, 30
    COL2 = 430
    FONT = "'Trebuchet MS','Segoe UI',Verdana,sans-serif"

    def text(x, y, s, fill, size=14, weight="400", anchor="start"):
        return ('<text x="%.1f" y="%d" fill="%s" font-size="%d" font-weight="%s" '
                'text-anchor="%s" font-family="%s">%s</text>'
                % (x, y, fill, size, weight, anchor, FONT, esc(s)))

    p = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
         'viewBox="0 0 %d %d" role="img" aria-label="GitHub stats for %s">'
         % (W, H, W, H, USER)]
    p.append('<rect x="1" y="1" width="%d" height="%d" rx="20" fill="%s" stroke="%s" stroke-width="2"/>'
             % (W - 2, H - 2, c["card"], c["border"]))

    # left column
    y = PAD + 22
    p.append(text(PAD + 4, y, "❀  a little about the code", c["accent"], 16, "700"))
    y += 34
    for label, value in data["stats"]:
        p.append('<circle cx="%d" cy="%d" r="3.2" fill="%s"/>' % (PAD + 8, y - 5, c["accent"]))
        p.append(text(PAD + 22, y, label, c["key"], 14))
        p.append(text(COL2 - 60, y, value, c["value"], 15, "700", "end"))
        y += 32

    # right column
    y = PAD + 22
    p.append(text(COL2, y, "✦  languages i reach for", c["accent"], 16, "700"))
    y += 34
    BAR_W, BAR_H = 190, 9
    for i, (name, pct) in enumerate(data["langs"]):
        p.append(text(COL2, y, name[:13], c["key"], 13))
        bx, by = COL2 + 110, y - 9
        p.append('<rect x="%d" y="%d" width="%d" height="%d" rx="4.5" fill="%s"/>'
                 % (bx, by, BAR_W, BAR_H, c["track"]))
        p.append('<rect x="%d" y="%d" width="%.1f" height="%d" rx="4.5" fill="%s"/>'
                 % (bx, by, max(5.0, BAR_W * pct / 100.0), BAR_H, BAR_COLORS[i % len(BAR_COLORS)]))
        p.append(text(bx + BAR_W + 46, y, "%.1f%%" % pct, c["value"], 12, "700", "end"))
        y += 28

    p.append(text(PAD + 4, H - 18, "regenerated by .github/workflows/stats.yml", c["key"], 10))
    p.append("</svg>")
    return "\n".join(p)


def main():
    if not os.path.isdir(OUT_DIR):
        os.makedirs(OUT_DIR)
    print("collecting %s ..." % USER)
    data = collect()
    for theme in THEMES:
        path = os.path.join(OUT_DIR, "stats-%s.svg" % theme)
        with io.open(path, "w", encoding="utf-8", newline=chr(10)) as f:
            f.write(render(data, theme))
        print("wrote %s" % path)
    for label, value in data["stats"]:
        print("  %-14s %s" % (label, value))
    for name, pct in data["langs"]:
        print("  %-14s %5.1f%%" % (name, pct))


if __name__ == "__main__":
    main()
