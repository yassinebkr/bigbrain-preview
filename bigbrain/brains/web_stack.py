"""Server-owned React/Vite toolchain and bounded subprocess execution."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import signal
from pathlib import Path

REACT_FILES = {
    "package.json": json.dumps(
        {
            "name": "bigbrain-generated-app",
            "version": "1.0.0",
            "private": True,
            "type": "module",
            "scripts": {"typecheck": "tsc --noEmit", "build": "vite build"},
            "dependencies": {"react": "19.2.0", "react-dom": "19.2.0", "lucide-react": "0.562.0"},
            "devDependencies": {
                "typescript": "5.9.3",
                "vite": "7.3.7",
                "@types/react": "19.2.5",
                "@types/react-dom": "19.2.3",
            },
        },
        indent=2,
    ),
    "tsconfig.json": json.dumps(
        {
            "compilerOptions": {
                "target": "ES2022",
                "lib": ["ES2022", "DOM", "DOM.Iterable"],
                "module": "ESNext",
                "moduleResolution": "Bundler",
                "jsx": "react-jsx",
                "strict": True,
                "skipLibCheck": True,
                "noEmit": True,
                "allowSyntheticDefaultImports": True,
                "resolveJsonModule": True,
            },
            "include": ["src"],
        },
        indent=2,
    ),
    "vite.config.ts": "export default { base: './', build: { outDir: 'dist', emptyOutDir: true } };\n",
}


def runtime_command(argv: list[str]) -> list[str]:
    if shutil.which("node") and shutil.which("npm"):
        return argv
    # Flatpak exposes the host npm CLI as files. Playwright already ships
    # a compatible local Node runtime, so temporary build directories need
    # not be visible to an external host process.
    try:
        import playwright

        node = Path(playwright.__file__).parent / "driver" / "node"
        npm = Path("/run/host/usr/share/nodejs/npm/bin/npm-cli.js")
        if node.is_file() and npm.is_file():
            return [str(node), *([str(npm)] if argv[0] == "npm" else []), *argv[1:]]
    except ImportError:
        pass
    if shutil.which("flatpak-spawn"):
        return ["flatpak-spawn", "--host", *argv]
    raise RuntimeError("React/Vite requires Node >=20.19 and npm on PATH")


async def command(project: Path, argv: list[str], timeout: int = 120) -> dict:
    process = await asyncio.create_subprocess_exec(
        *runtime_command(argv),
        cwd=str(project),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        start_new_session=(os.name == "posix"),
    )
    try:
        output, _ = await asyncio.wait_for(process.communicate(), timeout)
        return {
            "status": "passed" if process.returncode == 0 else "failed",
            "command": argv,
            "output": output.decode(errors="replace")[-16000:],
        }
    except asyncio.TimeoutError:
        return {"status": "inconclusive", "command": argv, "output": f"Timeout after {timeout}s"}
    finally:
        if process.returncode is None:
            if os.name == "posix":
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            else:
                process.kill()
            await process.wait()


async def build_react(project: Path) -> list[dict]:
    # Toolchain files are owned by BigBrain, never generated build scripts.
    for name, content in REACT_FILES.items():
        (project / name).write_text(content, encoding="utf-8")
    stages = []
    for name, argv in (
        ("dependencies", ["npm", "install", "--ignore-scripts", "--no-audit", "--no-fund"]),
        ("typecheck", ["node", "node_modules/typescript/bin/tsc", "--noEmit"]),
        ("build", ["node", "node_modules/vite/bin/vite.js", "build"]),
    ):
        stage = {"name": name, **await command(project, argv)}
        stages.append(stage)
        if stage["status"] != "passed":
            break
    return stages
