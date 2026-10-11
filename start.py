"""Start the API from the project root: python start.py"""

import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    backend = Path(__file__).resolve().parent / "Backend"
    if not (backend / "app" / "main.py").is_file():
        raise SystemExit(f"Backend app not found at {backend}")
    env = os.environ.copy()
    # .env uses Docker hostnames. Those names do not resolve on the host.
    env["MCP_PROBE"] = "false"
    return subprocess.call(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--reload", "--reload-dir", "app"],
        cwd=backend,
        env=env,
    )


if __name__ == "__main__":
    raise SystemExit(main())
