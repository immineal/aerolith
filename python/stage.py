"""Copy library/dist into the Python package before building (python -m build)."""
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
DIST = HERE.parent / "library" / "dist"
DEST = HERE / "src" / "aerolith" / "static" / "aerolith"

if DEST.exists():
    shutil.rmtree(DEST)
DEST.mkdir(parents=True)
for name in ("aerolith.css", "aerolith.js", "sprites.json"):
    shutil.copy2(DIST / name, DEST / name)
shutil.copytree(DIST / "sprites", DEST / "sprites")
shutil.copytree(DIST / "fonts", DEST / "fonts")
shutil.copy2(HERE.parent / "LICENSE", HERE / "LICENSE")
print(f"staged {sum(1 for _ in DEST.rglob('*'))} files -> {DEST}")
