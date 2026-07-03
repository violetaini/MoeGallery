import json
import sys
from datetime import datetime, timezone
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parent
ROOT_DIR = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.main import app  # noqa: E402


OUTPUT_DIR = ROOT_DIR / "docs" / "api"


def build_static_html(title: str) -> str:
    generated_at = datetime.now(timezone.utc).isoformat()
    return f"""<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{title}</title>
    <style>
      body {{ margin: 0; }}
      .build-meta {{
        position: fixed;
        right: 12px;
        bottom: 8px;
        z-index: 10;
        color: #6b7280;
        font: 12px/1.5 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        pointer-events: none;
      }}
    </style>
  </head>
  <body>
    <script
      id="api-reference"
      data-url="./openapi.json"
      data-theme="alternate"
      data-layout="modern"
    ></script>
    <script src="https://cdn.jsdelivr.net/npm/@scalar/api-reference"></script>
    <div class="build-meta">Generated {generated_at}</div>
  </body>
</html>
"""


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    app.openapi_schema = None
    schema = app.openapi()
    (OUTPUT_DIR / "openapi.json").write_text(
        json.dumps(schema, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (OUTPUT_DIR / "index.html").write_text(
        build_static_html(schema["info"]["title"]),
        encoding="utf-8",
    )
    print(f"Wrote {OUTPUT_DIR / 'openapi.json'}")
    print(f"Wrote {OUTPUT_DIR / 'index.html'}")


if __name__ == "__main__":
    main()
