"""Tiny SVG flowchart generator for the loop-engineering lab stage charts."""

import sys
from html import escape

W = 900
COL_X = {-1: 150, 0: 450, 1: 750}
ROW_H = 84
TOP = 110

PALETTE = {
    "plain": ("#FFFFFF", "#888780", "#2C2C2A"),
    "new": ("#FAECE7", "#D85A30", "#712B13"),      # added in this stage
    "done": ("#EAF3DE", "#3B6D11", "#27500A"),
    "bad": ("#FCEBEB", "#A32D2D", "#791F1F"),
    "model": ("#EEEDFE", "#7F77DD", "#3C3489"),
    "term": ("#F1EFE8", "#5F5E5A", "#2C2C2A"),
}


class Node:
    def __init__(self, key, col, row, text, kind="box", color="plain", width=250):
        self.key, self.col, self.row, self.kind, self.color, self.width = key, col, row, kind, color, width
        self.lines = text.split("\n")
        self.x = COL_X[col]
        self.y = TOP + row * ROW_H
        self.h = 64 if kind == "diamond" else max(44, 20 + 18 * len(self.lines))

    def top(self): return (self.x, self.y - self.h / 2)
    def bottom(self): return (self.x, self.y + self.h / 2)
    def left(self): return (self.x - self.width / 2, self.y)
    def right(self): return (self.x + self.width / 2, self.y)

    def svg(self):
        fill, stroke, text = PALETTE[self.color]
        x, y, w, h = self.x, self.y, self.width, self.h
        if self.kind == "diamond":
            pts = f"{x},{y-h/2} {x+w/2},{y} {x},{y+h/2} {x-w/2},{y}"
            shape = f'<polygon points="{pts}" fill="{fill}" stroke="{stroke}" stroke-width="1.2"/>'
        else:
            rx = h / 2 if self.kind == "term" else 8
            shape = f'<rect x="{x-w/2}" y="{y-h/2}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="1.2"/>'
        start = y - (len(self.lines) - 1) * 9
        texts = "".join(
            f'<text x="{x}" y="{start + i*18 + 4.5}" font-size="{13.5 if i == 0 else 12.5}" '
            f'font-weight="{600 if i == 0 else 400}" fill="{text}" text-anchor="middle">{escape(line)}</text>'
            for i, line in enumerate(self.lines)
        )
        return shape + texts


def edge(points, label=None, label_at=None, color="#5F5E5A", dashed=False, anchor="start"):
    d = "M" + " L".join(f"{px},{py}" for px, py in points)
    dash = ' stroke-dasharray="5 4"' if dashed else ""
    out = f'<path d="{d}" fill="none" stroke="{color}" stroke-width="1.4"{dash} marker-end="url(#a)"/>'
    if label:
        lx, ly = label_at or ((points[0][0] + points[1][0]) / 2 + 8, (points[0][1] + points[1][1]) / 2 - 4)
        out += f'<text x="{lx}" y="{ly}" font-size="12" font-weight="600" fill="{color}" text-anchor="{anchor}">{escape(label)}</text>'
    return out


def render(path, title, subtitle, nodes, edges, legend_new, result_lines, height):
    body = [n.svg() for n in nodes.values()] + edges
    ry = height - 34 - 20 * len(result_lines)
    result = (
        f'<rect x="30" y="{ry - 26}" width="{W-60}" height="{20*len(result_lines) + 20}" rx="10" fill="#F1EFE8" stroke="#B4B2A9"/>'
        + "".join(
            f'<text x="48" y="{ry + i*20 - 2}" font-size="13" fill="#2C2C2A" font-weight="{600 if i == 0 else 400}">{escape(t)}</text>'
            for i, t in enumerate(result_lines)
        )
    )
    legend = (
        f'<rect x="{W-300}" y="54" width="16" height="12" rx="3" fill="#FAECE7" stroke="#D85A30"/>'
        f'<text x="{W-278}" y="64" font-size="12" fill="#5F5E5A">{escape(legend_new)}</text>'
    )
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{height}" viewBox="0 0 {W} {height}" font-family="-apple-system, 'Segoe UI', Helvetica, Arial, sans-serif">
<title>{escape(title)}</title>
<defs><marker id="a" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M2 1L8 5L2 9" fill="none" stroke="context-stroke" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></marker></defs>
<rect width="{W}" height="{height}" fill="#FFFFFF"/>
<text x="30" y="40" font-size="21" font-weight="600" fill="#2C2C2A">{escape(title)}</text>
<text x="30" y="64" font-size="13.5" fill="#5F5E5A">{escape(subtitle)}</text>
{legend}
{"".join(body)}
{result}
</svg>'''
    open(path, "w").write(svg)
