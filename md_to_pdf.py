"""Render ASSESSMENT.md to a styled PDF via Microsoft Edge headless mode."""
import subprocess
import sys
from pathlib import Path

import markdown

ROOT = Path(__file__).parent
MD = ROOT / "ASSESSMENT.md"
HTML = ROOT / "ASSESSMENT.html"
PDF = ROOT / "ASSESSMENT.pdf"
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

CSS = """
@page { size: A4; margin: 18mm 16mm; }
html { font-size: 11pt; }
body {
    font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
    color: #1f2328;
    line-height: 1.5;
    max-width: 100%;
    margin: 0;
}
h1 {
    font-size: 22pt;
    border-bottom: 2px solid #d0d7de;
    padding-bottom: 6px;
    margin-top: 0;
    margin-bottom: 12px;
}
h2 {
    font-size: 16pt;
    border-bottom: 1px solid #d0d7de;
    padding-bottom: 4px;
    margin-top: 24px;
    page-break-after: avoid;
}
h3 {
    font-size: 13pt;
    margin-top: 18px;
    page-break-after: avoid;
}
p, li { font-size: 10.5pt; }
ul, ol { padding-left: 22px; }
li { margin: 2px 0; }
code {
    font-family: "Cascadia Mono", Consolas, "Courier New", monospace;
    font-size: 9.5pt;
    background: #f6f8fa;
    padding: 1px 4px;
    border-radius: 3px;
}
pre {
    background: #f6f8fa;
    border: 1px solid #d0d7de;
    border-radius: 6px;
    padding: 10px 12px;
    overflow-x: auto;
    page-break-inside: avoid;
}
pre code {
    background: transparent;
    padding: 0;
    font-size: 9pt;
    line-height: 1.4;
}
table {
    border-collapse: collapse;
    width: 100%;
    margin: 10px 0;
    font-size: 9.5pt;
    page-break-inside: auto;
}
th, td {
    border: 1px solid #d0d7de;
    padding: 6px 10px;
    text-align: left;
    vertical-align: top;
}
th {
    background: #f6f8fa;
    font-weight: 600;
}
hr { border: 0; border-top: 1px solid #d0d7de; margin: 20px 0; }
strong { color: #1f2328; }
a { color: #0969da; text-decoration: none; }
blockquote {
    border-left: 3px solid #d0d7de;
    color: #57606a;
    padding: 0 12px;
    margin: 8px 0;
}
"""


def main() -> None:
    md_text = MD.read_text(encoding="utf-8")
    html_body = markdown.markdown(
        md_text,
        extensions=["tables", "fenced_code", "sane_lists"],
    )
    html_doc = f"""<!doctype html>
<html lang="nl">
<head>
<meta charset="utf-8">
<title>Assessment — Swoep.AI</title>
<style>{CSS}</style>
</head>
<body>
{html_body}
</body>
</html>
"""
    HTML.write_text(html_doc, encoding="utf-8")
    print(f"Wrote {HTML}")

    if not Path(EDGE).exists():
        sys.exit(f"Edge niet gevonden op {EDGE}")

    cmd = [
        EDGE,
        "--headless=new",
        "--disable-gpu",
        "--no-pdf-header-footer",
        f"--print-to-pdf={PDF}",
        HTML.as_uri(),
    ]
    print("Running Edge headless...")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        print("STDOUT:", result.stdout)
        print("STDERR:", result.stderr)
        sys.exit(f"Edge exited with code {result.returncode}")
    print(f"Wrote {PDF}")


if __name__ == "__main__":
    main()
