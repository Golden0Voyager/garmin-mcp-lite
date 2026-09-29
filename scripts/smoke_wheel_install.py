#!/usr/bin/env python3
"""Packaging smoke test: install the built wheel into a throwaway environment,
lock-file-free, and make it speak MCP.

Why this exists
---------------
The `mcp` upper bound was missing for several releases, so `uvx
garmin-mcp-lite` resolved mcp 2.x (which removed ``mcp.server.fastmcp``) and the
server died at import.  CI never caught it because it installed with
``uv sync``, which honours ``uv.lock`` -- and the lock pinned a working mcp.
Only lock-ignoring installers (uvx, plain pip) resolved the published metadata
and hit the breakage.

So this script deliberately reproduces the *lock-ignoring* path:

1. build a wheel from the working tree;
2. create a clean venv and install **that wheel** with no lock and no
   ``--with`` override, so dependency resolution comes only from the wheel
   metadata;
3. assert the resolved ``mcp`` satisfies the declared constraint;
4. run a real MCP ``initialize`` + ``tools/list`` handshake in the child.

It runs in CI and is safe to run locally:  python3 scripts/smoke_wheel_install.py
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TIMEOUT = 300


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT, **kw)


def fail(msg: str) -> None:
    print(f"FAIL: {msg}")
    sys.exit(1)


def build_wheel(workdir: Path) -> Path:
    """Build sdist+wheel into an isolated dist dir so the repo's dist/ is untouched."""
    dist = workdir / "dist"
    p = run(["uv", "build", "--out-dir", str(dist)], cwd=ROOT)
    if p.returncode != 0:
        fail(f"uv build failed:\n{p.stdout[-1500:]}\n{p.stderr[-1500:]}")
    wheels = sorted(dist.glob("*.whl"))
    if len(wheels) != 1:
        fail(f"expected exactly one wheel, got {[w.name for w in wheels]}")
    return wheels[0]


def parse_requires_dist(wheel: Path) -> dict[str, str]:
    """Read Requires-Dist out of the wheel's METADATA without importing it."""
    import zipfile

    with zipfile.ZipFile(wheel) as zf:
        names = [n for n in zf.namelist() if n.endswith(".dist-info/METADATA")]
        if not names:
            fail("wheel has no .dist-info/METADATA")
        raw = zf.read(names[0]).decode("utf-8", "replace")
    out: dict[str, str] = {}
    for line in raw.splitlines():
        if line.startswith("Requires-Dist:"):
            spec = line.split(":", 1)[1].strip()
            m = re.match(r"^([A-Za-z0-9._-]+)", spec)
            if m:
                out[m.group(1).lower()] = spec
    return out


def resolve_mcp(env_python: Path) -> str:
    p = run(["uv", "pip", "show", "--python", str(env_python), "mcp"])
    if p.returncode != 0:
        fail(f"mcp was not installed into the clean environment:\n{p.stdout}\n{p.stderr}")
    m = re.search(r"^Version:\s*(\S+)", p.stdout, re.M)
    if not m:
        fail(f"could not parse installed mcp version from:\n{p.stdout}")
    return m.group(1)


def version_tuple(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3]) or (0,)


def handshake(env_python: Path) -> tuple[str, int]:
    """Drive the installed server over stdio: initialize, initialized, tools/list."""
    msgs = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                    "clientInfo": {"name": "smoke", "version": "1.0"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    ]
    payload = "\n".join(json.dumps(m) for m in msgs) + "\n"
    p = subprocess.run([str(env_python), "-m", "garmin_mcp_lite.server"],
                       input=payload, capture_output=True, text=True, timeout=TIMEOUT)
    if os.environ.get("SMOKE_DEBUG"):
        print("  [debug] rc:", p.returncode)
        print("  [debug] stdout:", repr((p.stdout or "")[:800]))
        print("  [debug] stderr:", repr((p.stderr or "")[:400]))

    server_name, n_tools = "", 0
    for line in (p.stdout or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        result = msg.get("result")
        if msg.get("id") == 1 and isinstance(result, dict):
            info = result.get("serverInfo")
            server_name = info.get("name", "") if isinstance(info, dict) else ""
        elif msg.get("id") == 2 and isinstance(result, dict):
            n_tools = len(result.get("tools") or [])
    return server_name, n_tools


def main() -> None:
    if not shutil.which("uv"):
        fail("uv not on PATH")

    workdir = Path(tempfile.mkdtemp(prefix="gmcp-smoke-"))
    try:
        wheel = build_wheel(workdir)
        print(f"[1/4] built {wheel.name}")

        requires = parse_requires_dist(wheel)
        mcp_spec = requires.get("mcp", "")
        print(f"[2/4] wheel requires mcp{mcp_spec[len('mcp'):] if mcp_spec else ' <none>'}")
        if not mcp_spec:
            fail("wheel does not declare an mcp dependency at all")
        # A bare lower bound is what caused the 0.1.3 outage: the resolver is then free
        # to take a future major that removes the modules server.py imports.
        if "<" not in mcp_spec and "!=" not in mcp_spec:
            fail(
                f"mcp requirement {mcp_spec!r} has no upper bound. An unbounded "
                "major release can remove the modules garmin_mcp_lite.server "
                "imports, and lock-ignoring installers (uvx, pip) will break. "
                "Cap it, e.g. 'mcp>=1.6.0,<2.0'."
            )

        env_dir = workdir / "venv"
        p = run(["uv", "venv", "--python", "3.12", str(env_dir)])
        if p.returncode != 0:
            fail(f"uv venv failed:\n{p.stderr[-800:]}")
        env_python = env_dir / "bin" / "python"

        # No --with, no --no-cache, no lock: resolution comes only from wheel metadata.
        p = run(["uv", "pip", "install", "--python", str(env_python), str(wheel)])
        if p.returncode != 0:
            fail(f"clean install of the wheel failed:\n{p.stdout[-1200:]}\n{p.stderr[-1200:]}")

        mcp_version = resolve_mcp(env_python)
        print(f"[3/4] clean install resolved mcp {mcp_version}")

        upper = re.search(r"<\s*(\d+(?:\.\d+)*)", mcp_spec)
        if upper and version_tuple(mcp_version) >= version_tuple(upper.group(1)):
            fail(
                f"installed mcp {mcp_version} violates the declared bound {mcp_spec!r}; "
                "a lock-ignoring installer would break."
            )

        name, n_tools = handshake(env_python)
        if not name:
            fail("MCP initialize returned no serverInfo")
        if n_tools < 1:
            fail("tools/list returned 0 tools")
        print(f"[4/4] handshake OK: {name} v{mcp_version}, {n_tools} tools")
        print("\nPASS: the published wheel installs lock-free and speaks MCP.")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    main()
