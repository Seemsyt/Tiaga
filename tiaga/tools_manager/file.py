from langchain_core.tools import tool
from pathlib import Path
import shutil


# ── Read ───────────────────────────────────────────────────────────────────────

def read_file(path: str) -> str:
    """Read and return the contents of a file. Use absolute or relative paths."""
    p = Path(path).expanduser().resolve()
    if not p.exists():
        return f"Error: '{path}' does not exist"
    if not p.is_file():
        return f"Error: '{path}' is not a file"
    try:
        return p.read_text()
    except Exception as e:
        return f"Error reading file: {e}"


# ── Write / Create ─────────────────────────────────────────────────────────────

def write_file(path: str, content: str) -> str:
    """
    Write content to a file. Creates the file and any missing parent
    directories automatically. Overwrites if the file already exists.
    Use absolute paths or paths relative to cwd.
    """
    p = Path(path).expanduser().resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return f"Written: '{p}'"

def create_folder(path: str) -> str:
    """Create a folder and any missing parents."""
    p = Path(path).expanduser().resolve()
    if p.exists():
        return f"Already exists: '{p}'"
    p.mkdir(parents=True)
    return f"Folder created: '{p}'"


# ── Edit ───────────────────────────────────────────────────────────────────────

def replace_in_file(path: str, old: str, new: str) -> str:
    """
    Replace the first occurrence of `old` with `new` inside a file.
    Prefer this over write_file for targeted edits — less token usage,
    less risk of corrupting the rest of the file.
    """
    p = Path(path).expanduser().resolve()
    if not p.exists():
        return f"Error: '{path}' does not exist"
    text = p.read_text()
    if old not in text:
        return f"Error: pattern not found in '{p}'"
    p.write_text(text.replace(old, new, 1))
    return f"Replaced in '{p}'"

def append_to_file(path: str, content: str) -> str:
    """Append content to the end of an existing file."""
    p = Path(path).expanduser().resolve()
    if not p.exists():
        return f"Error: '{path}' does not exist"
    with p.open("a") as f:
        f.write(content)
    return f"Appended to '{p}'"


# ── Delete ─────────────────────────────────────────────────────────────────────


def delete_item(path: str) -> str:
    """Delete a file or folder (recursive)."""
    p = Path(path).expanduser().resolve()
    if not p.exists():
        return f"Error: '{path}' does not exist"
    if p.is_file():
        p.unlink()
    else:
        shutil.rmtree(p)
    return f"Deleted: '{p}'"


# ── Navigate ───────────────────────────────────────────────────────────────────

def list_files(path: str = ".") -> str:
    """List files and folders at a path. Defaults to current directory."""
    p = Path(path).expanduser().resolve()
    if not p.exists():
        return f"Error: '{path}' does not exist"
    if not p.is_dir():
        return f"Error: '{path}' is not a directory"
    items = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name))
    if not items:
        return "Empty directory"
    return "\n".join(f"{'[file]' if i.is_file() else '[dir] '} {i.name}" for i in items)

def file_tree(path: str = ".", depth: int = 3) -> str:
    """
    Return an indented tree of the directory. Defaults to current directory.
    Call this first to understand a project's structure before editing.
    """
    p = Path(path).expanduser().resolve()
    if not p.exists():
        return f"Error: '{path}' does not exist"

    def _tree(current: Path, prefix: str, current_depth: int) -> list[str]:
        if current_depth == 0:
            return [prefix + "    ..."]
        lines = []
        items = sorted(current.iterdir(), key=lambda x: (x.is_file(), x.name))
        for i, item in enumerate(items):
            connector = "└── " if i == len(items) - 1 else "├── "
            lines.append(prefix + connector + item.name)
            if item.is_dir():
                extension = "    " if i == len(items) - 1 else "│   "
                lines.extend(_tree(item, prefix + extension, current_depth - 1))
        return lines

    return "\n".join([str(p)] + _tree(p, "", depth))


def move_item(src: str, dst: str) -> str:
    """Move or rename a file or folder."""
    s = Path(src).expanduser().resolve()
    d = Path(dst).expanduser().resolve()
    if not s.exists():
        return f"Error: '{src}' does not exist"
    d.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(s), str(d))
    return f"Moved '{s}' → '{d}'"


def get_cwd() -> str:
    """Return the current working directory. Call this first if the user
    refers to files without giving an absolute path."""
    return str(Path.cwd())


class FileService:

    @staticmethod
    def read(path: str):
        return read_file(path)

    @staticmethod
    def write(path: str, content: str):
        return write_file(path, content)

    @staticmethod
    def append(path: str, content: str):
        return append_to_file(path, content)

    @staticmethod
    def delete(path: str):
        return delete_item(path)

    @staticmethod
    def move(src: str, dest: str):
        return move_item(src, dest)

    @staticmethod
    def list(path: str = "."):
        return list_files(path)

    @staticmethod
    def tree(path: str = "."):
        return file_tree(path)

    @staticmethod
    def mkdir(path: str):
        return create_folder(path)

    @staticmethod
    def cwd():
        return get_cwd()