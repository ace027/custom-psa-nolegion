"""Export the OpenAPI spec to docs/api/openapi.json.

python -m app.openapi_export          # write the file
python -m app.openapi_export --check  # exit 1 when the committed file is stale
"""

import json
import sys
from pathlib import Path

SPEC_PATH = Path(__file__).resolve().parents[2] / "docs" / "api" / "openapi.json"


def generate() -> str:
    from app.main import app

    return json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    spec = generate()
    if "--check" in args:
        current = SPEC_PATH.read_text() if SPEC_PATH.exists() else None
        if current != spec:
            print(
                f"{SPEC_PATH} is stale. Regenerate it with: python -m app.openapi_export",
                file=sys.stderr,
            )
            return 1
        return 0
    SPEC_PATH.parent.mkdir(parents=True, exist_ok=True)
    SPEC_PATH.write_text(spec)
    print(f"wrote {SPEC_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
