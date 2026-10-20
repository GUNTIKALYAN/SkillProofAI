"""Start the app from the project root: python start.py

http://127.0.0.1:8000/ is the login page. The API listens on port 8002.
The MCP server listens on port 8010.
"""

import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

API_PORT = "8002"
MCP_PORT = "8010"
MCP_CONTAINER = "skillproof-mcp"
NEO4J_CONTAINER = "skillproof-neo4j"


def _libpq_dir() -> Path | None:
    roots = [
        Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "PostgreSQL",
        Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")) / "PostgreSQL",
    ]
    found: list[Path] = []
    for root in roots:
        if root.is_dir():
            found.extend(root.glob("*/bin/libpq.dll"))
    if not found:
        return None

    def version_key(dll: Path) -> tuple[int, ...]:
        parts = [int(part) if part.isdigit() else 0 for part in dll.parent.parent.name.split(".")]
        return tuple(parts)

    return max(found, key=version_key).parent


def _load_env(path: Path, env: dict[str, str]) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in env:
            env[key] = value


def _port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), 1):
            return True
    except OSError:
        return False


def _container_health(name: str) -> str:
    result = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Health.Status}}", name],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _docker_start(name: str) -> None:
    started = subprocess.run(["docker", "start", name], capture_output=True, text=True)
    if started.returncode != 0:
        raise SystemExit(f"{name} is not running. Start Docker, then run: docker start {name}")


def _ensure_neo4j() -> None:
    if _container_health(NEO4J_CONTAINER) == "healthy":
        return
    _docker_start(NEO4J_CONTAINER)
    for _ in range(40):
        if _container_health(NEO4J_CONTAINER) == "healthy":
            return
        time.sleep(2)
    raise SystemExit("Neo4j did not become ready.")


def _ensure_mcp(env: dict[str, str]) -> None:
    uri = env.get("NEO4J_URI", "")
    if not uri.startswith("neo4j+s://"):
        _ensure_neo4j()
    port = int(MCP_PORT)
    if _port_open(port):
        return
    _docker_start(MCP_CONTAINER)
    for _ in range(30):
        if _port_open(port):
            return
        time.sleep(1)
    raise SystemExit(f"MCP server did not open port {MCP_PORT}.")


def _wait_for_api(process: subprocess.Popen[bytes]) -> None:
    deadline = time.time() + 90
    url = f"http://127.0.0.1:{API_PORT}/healthz"
    while time.time() < deadline:
        if process.poll() is not None:
            raise SystemExit("API exited during startup.")
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, TimeoutError, OSError):
            time.sleep(0.5)
    raise SystemExit("API did not become ready.")


def _stop(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()


def main() -> int:
    root = Path(__file__).resolve().parent
    backend = root / "Backend"
    gateway = root / "gateway"
    if not (backend / "app" / "main.py").is_file():
        raise SystemExit(f"Backend app not found at {backend}")
    if not (gateway / "main.py").is_file():
        raise SystemExit(f"Gateway app not found at {gateway}")
    env = os.environ.copy()
    _load_env(root / ".env", env)
    _ensure_mcp(env)
    # Port 8001 is another local service. This app's MCP server is on 8010.
    env["MCP_URL"] = f"http://127.0.0.1:{MCP_PORT}/mcp"
    env["MCP_PROBE"] = "true"
    env["BACKEND_URL"] = f"http://127.0.0.1:{API_PORT}"
    env["FRONTEND_DIR"] = str(root / "Frontend")
    libpq = _libpq_dir()
    if libpq is not None:
        # The copy inside the virtualenv is blocked by Windows Application Control.
        env["PSYCOPG_IMPL"] = "python"
        env["PATH"] = str(libpq) + os.pathsep + env.get("PATH", "")
    api = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            API_PORT,
            "--reload",
            "--reload-dir",
            "app",
        ],
        cwd=backend,
        env=env,
    )
    try:
        _wait_for_api(api)
    except BaseException:
        _stop(api)
        raise
    try:
        return subprocess.call(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "main:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8000",
                "--reload",
                "--reload-dir",
                ".",
            ],
            cwd=gateway,
            env=env,
        )
    finally:
        _stop(api)


if __name__ == "__main__":
    raise SystemExit(main())
