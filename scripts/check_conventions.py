import ast
import re
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = Path("backend/core/setting.py")
MARKDOWN_LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)\)|!\[[^\]]*\]\(([^)\s]+)\)")


def python_errors(path: Path) -> list[str]:
    errors: list[str] = []
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    in_backend = path.parts[0] == "backend" and "migrations" not in path.parts
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if in_backend and ast.get_docstring(node) is not None:
                line = node.body[0].lineno
                errors.append(f"{path}:{line}: docstring (docs/handbook/quy-uoc-code.md: no docstrings unless asked)")
        if in_backend and path != SETTINGS and isinstance(node, ast.Attribute) and node.attr in {"getenv", "environ"}:
            if isinstance(node.value, ast.Name) and node.value.id == "os":
                errors.append(f"{path}:{node.lineno}: os.{node.attr} outside {SETTINGS} (read config via Config)")
        if path.parts[:2] == ("backend", "agent_package"):
            module = None
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
            elif isinstance(node, ast.Import):
                module = " ".join(alias.name for alias in node.names)
            if module and "backend.modules" in module:
                errors.append(f"{path}:{node.lineno}: agent_package must not import backend.modules")
    return errors


def markdown_errors(path: Path) -> list[str]:
    errors: list[str] = []
    # docs/reports/README.md: reports are point-in-time snapshots and may cite docs removed since.
    if path.parts[:2] == ("docs", "reports") and path.name != "README.md":
        return errors
    text = (ROOT / path).read_text(encoding="utf-8")
    for line_number, line in enumerate(text.splitlines(), start=1):
        for match in MARKDOWN_LINK.finditer(line):
            target = (match.group(1) or match.group(2)).split("#", 1)[0]
            if not target or re.match(r"^[a-z][a-z0-9+.-]*:", target, re.IGNORECASE):
                continue
            if not (ROOT / path).parent.joinpath(unquote(target)).exists():
                errors.append(f"{path}:{line_number}: broken relative link {target}")
    return errors


def module_doc_errors() -> list[str]:
    errors: list[str] = []
    for module in sorted((ROOT / "backend/modules").iterdir()):
        if (module / "__init__.py").exists() and not (ROOT / "docs/handbook/modules" / module.name).is_dir():
            errors.append(f"backend/modules/{module.name}: missing docs/handbook/modules/{module.name}/")
    return errors


def tracked_files() -> list[Path]:
    paths = [*ROOT.glob("backend/**/*.py"), *ROOT.glob("tests/**/*.py"), *ROOT.glob("scripts/**/*.py")]
    paths += [*ROOT.glob("docs/**/*.md"), *ROOT.glob("*.md"), *ROOT.glob("frontend/*.md")]
    return [path.relative_to(ROOT) for path in paths if "__pycache__" not in path.parts]


def main(arguments: list[str]) -> int:
    paths = [Path(argument).resolve().relative_to(ROOT) for argument in arguments] if arguments else tracked_files()
    errors = [] if arguments else module_doc_errors()
    for path in paths:
        if path.suffix == ".py":
            errors += python_errors(path)
        elif path.suffix == ".md":
            errors += markdown_errors(path)
    print("\n".join(errors) or f"conventions ok ({len(paths)} files)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
