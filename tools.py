import os
import subprocess
import urllib.request
import re
from pathlib import Path

WORKSPACE = Path(os.path.dirname(os.path.abspath(__file__))) / "workspace"
WORKSPACE.mkdir(exist_ok=True)

SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "exec_shell",
            "description": "Execute a shell command on the device. Use for system operations, running scripts, managing processes, installing packages, git, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Shell command to execute"},
                    "timeout": {"type": "integer", "description": "Timeout seconds (default 30)"}
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read content of a file",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path (absolute or relative to workspace)"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write or overwrite a file with given content",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path"},
                    "content": {"type": "string", "description": "Content to write"}
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": "List files and directories at a path",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path (default: home directory)"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "web_fetch",
            "description": "Fetch and return text content from a URL",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to fetch"},
                    "max_chars": {"type": "integer", "description": "Max characters to return (default 3000)"}
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "python_exec",
            "description": "Execute Python code and return stdout/stderr output",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Python code to execute"}
                },
                "required": ["code"]
            }
        }
    }
]


def exec_shell(command, timeout=30):
    try:
        r = subprocess.run(
            command, shell=True, capture_output=True,
            text=True, timeout=int(timeout), cwd=str(WORKSPACE)
        )
        out = r.stdout.strip()
        err = r.stderr.strip()
        if out and err:
            return f"stdout:\n{out}\nstderr:\n{err}"
        return out or err or "(no output)"
    except subprocess.TimeoutExpired:
        return f"Timeout after {timeout}s"
    except Exception as e:
        return f"Error: {e}"


def read_file(path):
    try:
        p = Path(path).expanduser()
        if not p.is_absolute():
            p = WORKSPACE / path
        return p.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"Error: {e}"


def write_file(path, content):
    try:
        p = Path(path).expanduser()
        if not p.is_absolute():
            p = WORKSPACE / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"Wrote {len(content)} chars → {p}"
    except Exception as e:
        return f"Error: {e}"


def list_dir(path=None):
    try:
        p = Path(path).expanduser() if path else Path.home()
        if not p.is_absolute():
            p = WORKSPACE / path
        items = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name))
        lines = [f"{'📁' if i.is_dir() else '📄'} {i.name}" for i in items]
        return "\n".join(lines) or "(empty)"
    except Exception as e:
        return f"Error: {e}"


def web_fetch(url, max_chars=3000):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        clean = re.sub(r"<[^>]+>", " ", raw)
        clean = re.sub(r"\s+", " ", clean).strip()
        return clean[:max_chars] + ("…" if len(clean) > max_chars else "")
    except Exception as e:
        return f"Error: {e}"


def python_exec(code):
    try:
        r = subprocess.run(
            ["python3", "-c", code],
            capture_output=True, text=True,
            timeout=30, cwd=str(WORKSPACE)
        )
        out = r.stdout.strip()
        err = r.stderr.strip()
        if out and err:
            return f"output:\n{out}\nerror:\n{err}"
        return out or err or "(no output)"
    except subprocess.TimeoutExpired:
        return "Timeout after 30s"
    except Exception as e:
        return f"Error: {e}"


_DISPATCH = {
    "exec_shell":  lambda a: exec_shell(**a),
    "read_file":   lambda a: read_file(**a),
    "write_file":  lambda a: write_file(**a),
    "list_dir":    lambda a: list_dir(**a),
    "web_fetch":   lambda a: web_fetch(**a),
    "python_exec": lambda a: python_exec(**a),
}

def dispatch(name, args):
    fn = _DISPATCH.get(name)
    return fn(args) if fn else f"Unknown tool: {name}"
