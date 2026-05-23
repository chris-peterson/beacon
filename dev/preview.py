"""Generate a marginalia-overlay preview gallery for visual review.

Renders a representative set of inputs through compose_note and emits
an HTML index alongside the PNGs. Open `.preview/index.html` in a
browser (or run `just preview`) to review changes to the renderer
without invoking iTerm2.
"""

from __future__ import annotations

import html
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "bin"))

from _compose import compose_note  # noqa: E402

OUT_DIR = REPO_ROOT / ".preview"
IMG_DIR = OUT_DIR / "img"

CASES: list[tuple[str, str, str]] = [
    (
        "simple-inline",
        "PAUSED",
        "thinking about this *carefully*",
    ),
    (
        "multi-line-heading",
        "WORKING",
        "Refreshing\nbackground data refresh in progress",
    ),
    (
        "screenshot-style",
        "WORKING",
        "Refreshing forge data\ntriaging loose ends",
    ),
    (
        "list-items",
        "WORKING",
        "decision needed\n"
        "* option one\n"
        "* option ~old plan~\n"
        "* option three",
    ),
    (
        "strikethrough-multiword",
        "PAUSED",
        "we should ~remove the entire fallback path~ before merging",
    ),
    (
        "strikethrough-mid-sentence",
        "PAUSED",
        "old plan: ~scrap it~ — going with the new one",
    ),
    (
        "inline-bold-italic-strike",
        "WORKING",
        "investigating *_critical_* edge case in ~the legacy~ renderer",
    ),
    (
        "mixed-blocks",
        "WORKING",
        "Background refresh\n"
        "running triage on 32 routes\n"
        "* Allow republishing supported disco tags\n"
        "* Fix mapping; got consul-agent and consul-aws ~mixed up~\n"
        "decide: route both to ecommerce-infrastructure-patterns",
    ),
    (
        "long-paragraph-truncates",
        "WORKING",
        "heading\n" + "\n".join(f"word{i}" for i in range(200)),
    ),
    (
        "long-list-truncates",
        "WORKING",
        "many items\n" + "\n".join(f"* item {i}" for i in range(30)),
    ),
    (
        "wide-single-word",
        "WORKING",
        "deploy target\nrelease/ecommerce-infrastructure-patterns-2026",
    ),
]


HTML_DOC = """\
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>beacon — marginalia overlay preview</title>
<style>
:root {{
  --bg: #282a36;
  --fg: #f8f8f2;
  --comment: #6272a4;
  --accent: #ff79c6;
  --card: #44475a;
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  padding: 2.5rem;
  background: var(--bg);
  color: var(--fg);
  font: 15px/1.5 -apple-system, BlinkMacSystemFont, "Helvetica Neue", sans-serif;
}}
header {{ margin-bottom: 2rem; }}
h1 {{
  margin: 0 0 0.25rem;
  font-weight: 600;
  font-size: 1.5rem;
}}
.subtitle {{
  color: var(--comment);
  margin: 0;
}}
.case {{
  display: grid;
  grid-template-columns: minmax(280px, 1fr) 2fr;
  gap: 1.25rem;
  padding: 1.25rem;
  border-radius: 12px;
  background: var(--card);
  margin-bottom: 1.25rem;
}}
.meta {{ min-width: 0; }}
.meta h2 {{
  margin: 0 0 0.5rem;
  font-size: 1rem;
  font-weight: 600;
  color: var(--accent);
  font-family: "SF Mono", Menlo, monospace;
}}
.label {{
  display: inline-block;
  font-size: 0.7rem;
  letter-spacing: 0.12em;
  color: var(--comment);
  margin-bottom: 0.5rem;
  font-weight: 600;
}}
pre {{
  margin: 0;
  padding: 0.75rem;
  background: rgba(0, 0, 0, 0.25);
  border-radius: 6px;
  font-family: "SF Mono", Menlo, monospace;
  font-size: 13px;
  white-space: pre-wrap;
  word-break: break-word;
  color: var(--fg);
}}
img {{
  display: block;
  width: 100%;
  height: auto;
  border-radius: 6px;
  background: var(--bg);
}}
</style>
</head>
<body>
<header>
  <h1>beacon — marginalia overlay preview</h1>
  <p class="subtitle">Visual gallery for the compose pipeline. Re-run <code>just preview</code> after edits to refresh.</p>
</header>
{cases}
</body>
</html>
"""

CASE_HTML = """\
<section class="case">
  <div class="meta">
    <div class="label">{label}</div>
    <h2>{name}</h2>
    <pre>{source}</pre>
  </div>
  <img src="img/{name}.png" alt="{name}">
</section>
"""


def main() -> None:
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    parts = []
    for name, label, text in CASES:
        out = IMG_DIR / f"{name}.png"
        compose_note(label, text, out)
        parts.append(
            CASE_HTML.format(
                name=html.escape(name),
                label=html.escape(label),
                source=html.escape(text),
            )
        )
    index = OUT_DIR / "index.html"
    index.write_text(HTML_DOC.format(cases="\n".join(parts)))
    print(f"wrote {index}")
    print(f"  ({len(CASES)} cases)")


if __name__ == "__main__":
    main()
