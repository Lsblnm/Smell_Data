"""Render streamlined PAPER.md -> PAPER.html -> PAPER.pdf (headless Chrome)."""

import re
import subprocess
from pathlib import Path

import markdown

HERE = Path(__file__).resolve().parent
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

CSS = """
@page { size: A4; margin: 15mm 14mm 15mm 14mm; }
body {
  font-family: "PingFang SC", -apple-system, BlinkMacSystemFont, "Helvetica Neue", sans-serif;
  font-size: 10.8pt; line-height: 1.66; color: #1f2a36;
  max-width: 920px; margin: 24px auto 48px; padding: 0 16px;
}
@media print {
  body { font-size: 9.9pt; line-height: 1.56; margin: 0 auto; padding: 0 4px; }
}
h1 { font-size: 21pt; margin: 0.2em 0 0.15em; line-height: 1.3; color: #10202f; }
h2 { font-size: 14.5pt; border-bottom: 2px solid #1b7f79; padding-bottom: 4px; margin-top: 1.45em; color: #10202f; }
h3 { font-size: 11.8pt; color: #1b4f72; margin-top: 1.05em; margin-bottom: 0.4em; }
h1 + h2 { border: none; font-size: 12.5pt; color: #566573; font-weight: 500; margin-top: 0; }
p, li { margin: 0.45em 0; }
blockquote {
  border-left: 4px solid #1b7f79; background: #f3f8f8;
  margin: 0.65em 0 1em; padding: 0.5em 0.95em; color: #34495e; font-size: 9.5pt; border-radius: 0 4px 4px 0;
}
.tldr-box {
  background: #f6faf9; border: 1px solid #cfe4e2; border-radius: 8px;
  padding: 14px 16px; margin: 14px 0 18px; page-break-inside: avoid;
}
.tldr-title { font-size: 11.5pt; font-weight: 700; color: #1b7f79; margin-bottom: 10px; }
.tldr-item {
  background: #ffffff; border-left: 4px solid #1b7f79; border-radius: 4px;
  padding: 8px 12px; margin-bottom: 8px; box-shadow: 0 1px 2px rgba(0,0,0,0.03);
}
.tldr-item:nth-child(3) { border-left-color: #d9822b; }
.tldr-item:nth-child(4) { border-left-color: #5b4b9a; margin-bottom: 0; }
.tldr-q { font-weight: 700; color: #10202f; font-size: 10.4pt; margin-bottom: 2px; }
.tldr-a { color: #34495e; font-size: 9.7pt; line-height: 1.55; }
table {
  border-collapse: collapse; width: 100%; margin: 0.65em 0 1em;
  font-size: 8.6pt; line-height: 1.48; page-break-inside: avoid;
}
th { background: #eaf2f2; border-top: 1.5px solid #1f2a36; border-bottom: 1px solid #1f2a36; padding: 5px 6px; text-align: left; }
td { border-bottom: 0.5px solid #d5dbe1; padding: 4.5px 6px; vertical-align: top; }
tr:last-child td { border-bottom: 1.5px solid #1f2a36; }
img { width: 100%; margin: 0.5em 0 0.85em; page-break-inside: avoid; }
code { font-family: "SF Mono", Menlo, monospace; font-size: 8.8pt; background: #f2f4f6; padding: 1px 4px; border-radius: 3px; }
pre { background: #f4f6f7; padding: 8px 10px; border-radius: 4px; font-size: 8.5pt; overflow-x: auto; }
hr { border: none; border-top: 1px solid #dde3e8; margin: 1.25em 0; }
strong { color: #10202f; }
.katex-display { margin: 0.55em 0; overflow-x: auto; }
"""

HEAD = """<!doctype html><html lang="zh"><head><meta charset="utf-8"><title>代码坏味如何影响 AI 辅助开发</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.css">
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.js"></script>
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/contrib/auto-render.min.js"
 onload="renderMathInElement(document.body,{delimiters:[{left:'$$',right:'$$',display:true},{left:'$',right:'$',display:false}]});"></script>
<style>%s</style></head><body>"""


def main():
    text = (HERE / "PAPER.md").read_text()
    stash = []

    def keep(m):
        stash.append(m.group(0))
        return f"@@MATH{len(stash) - 1}@@"

    text = re.sub(r"\$\$.*?\$\$", keep, text, flags=re.S)
    text = re.sub(r"(?<!\\)\$[^$\n]+?\$", keep, text)
    html = markdown.markdown(text, extensions=["tables", "fenced_code"])
    for i, s in enumerate(stash):
        html = html.replace(f"@@MATH{i}@@", s.replace("<", "&lt;"))
    html = html.replace("\\*", "*")
    out = HERE / "PAPER.html"
    out.write_text(HEAD % CSS + html + "</body></html>")
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", "--virtual-time-budget=15000",
                    f"--print-to-pdf={HERE / 'PAPER.pdf'}", out.as_uri()], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print("wrote", out, HERE / "PAPER.pdf")


if __name__ == "__main__":
    main()
