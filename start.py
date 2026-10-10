"""Start the API from the project root: python start.py"""

import subprocess
import sys
from pathlib import Path


def main() -> int:
    backend = Path(__file__).resolve().parent / "Backend"
    if not (backend / "app" / "main.py").is_file():
        raise SystemExit(f"Backend app not found at {backend}")
    return subprocess.call(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--reload"],
        cwd=backend,
    )


if __name__ == "__main__":
    raise SystemExit(main())
