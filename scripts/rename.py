"""Rename the project everywhere: `python scripts/rename.py <new_name>` (package, CLI, env vars, docs)."""
import re
import subprocess
import sys
from pathlib import Path

OLD = "agentifyapi"


def main(new: str) -> None:
    if not re.fullmatch(r"[a-z][a-z0-9_]*", new):
        sys.exit("name must be a lowercase python identifier")
    files = subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=True).stdout.split()
    for f in files:
        p = Path(f)
        if p.suffix in {".png", ".jpg", ".db"} or not p.exists():
            continue
        text = p.read_text()
        out = text.replace(OLD, new).replace(OLD.upper(), new.upper())
        if out != text:
            p.write_text(out)
    subprocess.run(["git", "mv", f"src/{OLD}", f"src/{new}"], check=True)
    print(f"renamed {OLD} -> {new}; run `pip install -e .[dev] && pytest -q`")


if __name__ == "__main__":
    main(sys.argv[1])
