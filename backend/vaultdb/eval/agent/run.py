"""End-to-end agent eval: run Claude Code on UI tasks with no library, the MOC pasted in, or the MCP.

Run on a machine where `claude` is logged in (not over SSH on macOS: the login lives in the keychain).

    uv run python -m vaultdb.eval.agent.run --init-template /tmp/vaultdb-eval-template
    uv run python -m vaultdb.eval.agent.run --arm none --template /tmp/vaultdb-eval-template \
        --vault-path ~/Desktop/Claude/Components --out runs
    (repeat with --arm moc and --arm mcp), then:
    uv run python -m vaultdb.eval.agent.score runs --vault-path ~/Desktop/Claude/Components
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

TASKS = Path(__file__).with_name("tasks.jsonl")
ARMS = ("none", "moc", "mcp")
BASE_TOOLS = ["Read", "Edit", "Write", "Glob", "Grep", "Bash(npm install:*)", "Bash(npm run build:*)"]
MCP_TOOLS = ["mcp__vaultdb__search_components", "mcp__vaultdb__get_component", "mcp__vaultdb__list_components"]
CLAUDE_TIMEOUT_S = 900


def load_tasks() -> list[dict]:
    return [json.loads(line) for line in TASKS.read_text(encoding="utf-8").splitlines() if line.strip()]


def build_prompt(task: dict, arm: str, moc: str) -> str:
    base = ("In this Vite + React + TypeScript + Tailwind project, build the following UI in src/App.tsx "
            "(add files under src/ as needed and install any npm packages you use):\n\n"
            f"{task['prompt']}\n\nMake sure `npm run build` passes.")
    if arm == "moc":
        return f"COMPONENT LIBRARY INDEX (use these components where they fit):\n\n{moc}\n\n{base}"
    if arm == "mcp":
        return f"{base}\n\nCheck the component library (vaultdb tools) for a matching component and adapt it."
    return base


def claude_command(arm: str, prompt: str, cfg_path: Path, mcp_bin: str) -> list[str]:
    """The claude CLI call for one run. Every arm uses --strict-mcp-config so only the intended servers load."""
    servers = {"vaultdb": {"command": mcp_bin, "args": []}} if arm == "mcp" else {}
    Path(cfg_path).write_text(json.dumps({"mcpServers": servers}))
    tools = BASE_TOOLS + (MCP_TOOLS if arm == "mcp" else [])
    return ["claude", "-p", prompt, "--output-format", "json", "--permission-mode", "acceptEdits",
            "--strict-mcp-config", "--mcp-config", str(cfg_path), "--allowedTools", ",".join(tools)]


TEMPLATE_FILES = {
    "package.json": json.dumps({
        "name": "vaultdb-eval-app", "private": True, "type": "module",
        "scripts": {"dev": "vite", "build": "tsc -b && vite build"},
        "dependencies": {"react": "^19.0.0", "react-dom": "^19.0.0", "clsx": "^2.1.1", "tailwind-merge": "^3.0.0",
                         "class-variance-authority": "^0.7.1"},
        "devDependencies": {"vite": "^6.0.0", "@vitejs/plugin-react": "^4.3.4", "typescript": "~5.7.0",
                            "@types/react": "^19.0.0", "@types/react-dom": "^19.0.0", "@types/node": "^22.0.0",
                            "tailwindcss": "^4.0.0", "@tailwindcss/vite": "^4.0.0"},
    }, indent=2),
    "tsconfig.json": json.dumps({"compilerOptions": {
        "target": "ES2022", "lib": ["ES2022", "DOM", "DOM.Iterable"], "module": "ESNext", "moduleResolution": "bundler",
        "jsx": "react-jsx", "strict": True, "noEmit": True, "skipLibCheck": True, "allowImportingTsExtensions": True,
        "baseUrl": ".", "paths": {"@/*": ["./src/*"]}}, "include": ["src"]}, indent=2),
    "vite.config.ts": ('import { defineConfig } from "vite";\nimport react from "@vitejs/plugin-react";\n'
                       'import tailwindcss from "@tailwindcss/vite";\nimport path from "path";\n\n'
                       'export default defineConfig({ plugins: [react(), tailwindcss()],\n'
                       '  resolve: { alias: { "@": path.resolve(__dirname, "./src") } } });\n'),
    "index.html": ('<!doctype html>\n<html lang="en">\n  <head><meta charset="UTF-8" /><title>App</title></head>\n'
                   '  <body><div id="root"></div><script type="module" src="/src/main.tsx"></script></body>\n</html>\n'),
    "src/main.tsx": ('import { StrictMode } from "react";\nimport { createRoot } from "react-dom/client";\n'
                     'import "./index.css";\nimport App from "./App";\n\n'
                     'createRoot(document.getElementById("root")!).render(<StrictMode><App /></StrictMode>);\n'),
    "src/App.tsx": "export default function App() {\n  return <main className=\"min-h-screen\" />;\n}\n",
    "src/index.css": '@import "tailwindcss";\n',
    "src/lib/utils.ts": ('import { clsx, type ClassValue } from "clsx";\nimport { twMerge } from "tailwind-merge";\n\n'
                         "export function cn(...inputs: ClassValue[]) {\n  return twMerge(clsx(inputs));\n}\n"),
}


def init_template(dest: Path) -> None:
    for rel, content in TEMPLATE_FILES.items():
        path = dest / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    subprocess.run(["npm", "install", "--no-audit", "--no-fund"], cwd=dest, check=True)
    subprocess.run(["npm", "run", "build"], cwd=dest, check=True)


def run_task(task: dict, arm: str, template: Path, out: Path, moc: str, mcp_bin: str, dry_run: bool) -> dict:
    run_dir = out / arm / task["id"]
    project = run_dir / "project"
    if project.exists():
        shutil.rmtree(project)
    shutil.copytree(template, project, ignore=shutil.ignore_patterns("node_modules", "dist"))
    os.symlink(template / "node_modules", project / "node_modules")
    cmd = claude_command(arm, build_prompt(task, arm, moc), run_dir / "mcp.json", mcp_bin)
    if dry_run:
        print(" ".join(cmd[:2]) + " <prompt> " + " ".join(cmd[3:]))
        return {"dry_run": True}
    t = time.time()
    claude = subprocess.run(cmd, cwd=project, capture_output=True, text=True, timeout=CLAUDE_TIMEOUT_S)
    (run_dir / "claude.json").write_text(claude.stdout)
    build = subprocess.run(["npm", "run", "build"], cwd=project, capture_output=True, text=True)
    (run_dir / "build.log").write_text(build.stdout + build.stderr)
    result = {"claude_exit": claude.returncode, "build_ok": build.returncode == 0, "seconds": round(time.time() - t, 1)}
    (run_dir / "result.json").write_text(json.dumps(result))
    return result


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--init-template", type=Path, help="create the scratch Vite + React + Tailwind project here")
    ap.add_argument("--arm", choices=ARMS)
    ap.add_argument("--template", type=Path)
    ap.add_argument("--vault-path", type=Path)
    ap.add_argument("--out", type=Path, default=Path("runs"))
    ap.add_argument("--tasks", nargs="*", help="task ids (default: all)")
    ap.add_argument("--mcp-bin", default=shutil.which("vaultdb-mcp") or str(Path(sys.executable).with_name("vaultdb-mcp")))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    if args.init_template:
        init_template(args.init_template.expanduser())
        print(f"template ready: {args.init_template}")
        return
    if not (args.arm and args.template and args.vault_path):
        ap.error("--arm, --template and --vault-path are required to run tasks")
    moc = (args.vault_path.expanduser() / "Components-MOC.md").read_text(encoding="utf-8") if args.arm == "moc" else ""
    tasks = [t for t in load_tasks() if not args.tasks or t["id"] in args.tasks]
    for task in tasks:
        result = run_task(task, args.arm, args.template.expanduser(), args.out, moc, args.mcp_bin, args.dry_run)
        print(f"{args.arm}/{task['id']}: {result}", flush=True)


if __name__ == "__main__":
    main()
