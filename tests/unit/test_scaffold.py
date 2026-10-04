"""Tests for scripts/scaffold.py. Every test works inside pytest's tmp_path.

Place this file at tests/unit/test_scaffold.py (it finds scripts/scaffold.py
relative to its own location, so it works from any working directory).
"""

import importlib.util
import shutil
import sys
from pathlib import Path
from types import ModuleType

import pytest

_HERE = Path(__file__).resolve()
# Normal location first (tests/unit -> scripts/), then next to this file.
_CANDIDATES = [
    _HERE.parents[2] / "scripts" / "scaffold.py",
    _HERE.parent / "scaffold.py",
]


def _find_script() -> Path:
    for candidate in _CANDIDATES:
        if candidate.is_file():
            return candidate
    tried = "\n  ".join(str(c) for c in _CANDIDATES)
    raise FileNotFoundError(f"scaffold.py not found. Looked in:\n  {tried}")


SCRIPT = _find_script()


def _load(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None, f"cannot load {path}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclasses/enums need this
    spec.loader.exec_module(module)
    return module


scaffold_mod = _load(SCRIPT, "wbms_scaffold")


def _copy_script_to(folder: Path) -> ModuleType:
    """Load a private copy of scaffold.py placed inside ``folder``."""
    folder.mkdir(parents=True)
    target = folder / "scaffold.py"
    shutil.copy(SCRIPT, target)
    return _load(target, f"wbms_scaffold_{abs(hash(str(folder)))}")

# The tree from slide 25, written out by hand (independent of the script).
EXPECTED_FILES = [
    "README.md",
    ".env.example",
    "Makefile",
    "pyproject.toml",
    "requirements.txt",
    "requirements-dev.txt",
    "Dockerfile",
    "docker-compose.yml",
    "docs/README.md",
    "docs/architecture.md",
    "docs/api.md",
    "docs/adr/README.md",
    "scripts/init_db.py",
    "scripts/seed.py",
    "src/wbms/__init__.py",
    "src/wbms/config.py",
    "src/wbms/db.py",
    "src/wbms/schema.sql",
    "src/wbms/cli.py",
    "src/wbms/repositories/__init__.py",
    "src/wbms/services/__init__.py",
    "src/wbms/gateways/__init__.py",
    "src/wbms/gateways/payments/__init__.py",
    "src/wbms/gateways/routers/__init__.py",
    "src/wbms/web/__init__.py",
    "tests/README.md",
    "tests/conftest.py",
]
EXPECTED_DIRS = [
    "docs",
    "docs/adr",
    "scripts",
    "src",
    "src/wbms",
    "src/wbms/repositories",
    "src/wbms/services",
    "src/wbms/gateways",
    "src/wbms/gateways/payments",
    "src/wbms/gateways/routers",
    "src/wbms/web",
    "src/wbms/web/templates",
    "src/wbms/web/static",
    "tests",
    "tests/unit",
    "tests/integration",
]
PACKAGES = [p for p in EXPECTED_FILES if p.endswith("__init__.py")]
EMPTY_LEAF_DIRS = [
    "src/wbms/web/templates",
    "src/wbms/web/static",
    "tests/unit",
    "tests/integration",
]


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path / "wbms-lite"


def statuses(results: list, status: object) -> list[str]:
    return [r.path for r in results if r.status == status]


# --- creation -------------------------------------------------------------


def test_scaffold_creates_every_file_from_slide_25(root: Path) -> None:
    scaffold_mod.scaffold(root)
    missing = [f for f in EXPECTED_FILES if not (root / f).is_file()]
    assert missing == []


def test_scaffold_creates_every_directory_from_slide_25(root: Path) -> None:
    scaffold_mod.scaffold(root)
    missing = [d for d in EXPECTED_DIRS if not (root / d).is_dir()]
    assert missing == []


def test_scaffold_creates_missing_root_folder(root: Path) -> None:
    assert not root.exists()
    results = scaffold_mod.scaffold(root)
    assert root.is_dir()
    assert results[0].path == "." and results[0].status == scaffold_mod.Status.CREATED


@pytest.mark.parametrize("init_file", PACKAGES)
def test_python_package_gets_empty_init_file(root: Path, init_file: str) -> None:
    scaffold_mod.scaffold(root)
    assert (root / init_file).read_bytes() == b""


@pytest.mark.parametrize("readme", ["docs/README.md", "tests/README.md"])
def test_docs_and_tests_get_placeholder_readme(root: Path, readme: str) -> None:
    scaffold_mod.scaffold(root)
    text = (root / readme).read_text(encoding="utf-8")
    assert text.startswith("# ") and len(text.strip().splitlines()) >= 2


@pytest.mark.parametrize("folder", EMPTY_LEAF_DIRS)
def test_empty_leaf_directory_gets_gitkeep(root: Path, folder: str) -> None:
    scaffold_mod.scaffold(root)
    assert (root / folder / ".gitkeep").is_file()


def test_tests_are_not_python_packages(root: Path) -> None:
    scaffold_mod.scaffold(root)
    assert not (root / "tests" / "__init__.py").exists()


# --- .env.example ---------------------------------------------------------


def _env_pairs(root: Path) -> dict[str, str]:
    pairs: dict[str, str] = {}
    for line in (root / ".env.example").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            key, sep, value = line.partition("=")
            assert sep == "=", f"not KEY=value: {line!r}"
            pairs[key] = value
    return pairs


def test_env_example_contains_all_settings_keys(root: Path) -> None:
    scaffold_mod.scaffold(root)
    keys = set(_env_pairs(root))
    required = {
        "SECRET_KEY", "DATABASE_PATH", "PAYMENT_GATEWAY", "ROUTER_ADAPTER",
        "CALLBACK_SECRET", "DARAJA_CONSUMER_KEY", "DARAJA_CONSUMER_SECRET",
        "DARAJA_SHORTCODE", "DARAJA_PASSKEY", "DARAJA_BASE_URL",
    }
    assert required <= keys


def test_env_example_defaults_to_mock_adapters(root: Path) -> None:
    scaffold_mod.scaffold(root)
    pairs = _env_pairs(root)
    assert pairs["PAYMENT_GATEWAY"] == "mock"
    assert pairs["ROUTER_ADAPTER"] == "mock"


def test_env_example_values_are_obviously_fake_not_empty(root: Path) -> None:
    scaffold_mod.scaffold(root)
    secret_like = {k: v for k, v in _env_pairs(root).items()
                   if any(w in k for w in ("SECRET", "PASSKEY", "PASSWORD", "KEY"))}
    assert secret_like, "expected secret-like keys"
    for key, value in secret_like.items():
        assert value, f"{key} has no placeholder value"
        assert value.startswith(("change-me", "fake")), f"{key}={value!r} looks real"


# --- never overwrite ------------------------------------------------------


def test_existing_file_is_not_overwritten_and_is_reported_skipped(root: Path) -> None:
    root.mkdir()
    (root / "README.md").write_text("my own readme", encoding="utf-8")
    results = scaffold_mod.scaffold(root)
    assert (root / "README.md").read_text(encoding="utf-8") == "my own readme"
    assert "README.md" in statuses(results, scaffold_mod.Status.SKIPPED)


def test_existing_empty_file_is_also_not_overwritten(root: Path) -> None:
    (root / "src" / "wbms").mkdir(parents=True)
    (root / "src" / "wbms" / "config.py").write_text("", encoding="utf-8")
    scaffold_mod.scaffold(root)
    assert (root / "src" / "wbms" / "config.py").read_text(encoding="utf-8") == ""


def test_second_run_creates_nothing_and_changes_nothing(root: Path) -> None:
    scaffold_mod.scaffold(root)
    before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    second = scaffold_mod.scaffold(root)
    after = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    assert before == after
    assert statuses(second, scaffold_mod.Status.CREATED) == []


def test_files_the_user_already_has_are_skipped_others_created(root: Path) -> None:
    root.mkdir()
    for name in ("README.md", "requirements.txt", "requirements-dev.txt"):
        (root / name).write_text("mine", encoding="utf-8")
    results = scaffold_mod.scaffold(root)
    skipped = set(statuses(results, scaffold_mod.Status.SKIPPED))
    assert {"README.md", "requirements.txt", "requirements-dev.txt"} <= skipped
    assert (root / "Makefile").is_file()


def test_unrelated_user_files_are_left_alone(root: Path) -> None:
    root.mkdir()
    (root / "phone.py").write_text("print('hi')", encoding="utf-8")
    scaffold_mod.scaffold(root)
    assert (root / "phone.py").read_text(encoding="utf-8") == "print('hi')"


def test_file_where_a_folder_should_be_is_a_conflict_not_a_crash(root: Path) -> None:
    root.mkdir()
    (root / "docs").write_text("oops, a file", encoding="utf-8")
    results = scaffold_mod.scaffold(root)
    assert "docs" in statuses(results, scaffold_mod.Status.CONFLICT)
    assert (root / "docs").read_text(encoding="utf-8") == "oops, a file"
    assert (root / "src" / "wbms" / "__init__.py").is_file()  # the rest still built


# --- dry run --------------------------------------------------------------


def test_dry_run_writes_nothing_even_the_root(root: Path) -> None:
    results = scaffold_mod.scaffold(root, dry_run=True)
    assert not root.exists()
    assert results and all(r.status == scaffold_mod.Status.WOULD_CREATE for r in results)


def test_dry_run_in_existing_folder_adds_no_files(tmp_path: Path) -> None:
    scaffold_mod.scaffold(tmp_path, dry_run=True)
    assert list(tmp_path.iterdir()) == []


def test_dry_run_plan_matches_real_run(root: Path, tmp_path: Path) -> None:
    planned = {r.path for r in scaffold_mod.scaffold(tmp_path / "ghost", dry_run=True)}
    real = {r.path for r in scaffold_mod.scaffold(root)}
    assert planned == real


def test_dry_run_still_reports_existing_files_as_skipped(root: Path) -> None:
    root.mkdir()
    (root / "README.md").write_text("mine", encoding="utf-8")
    results = scaffold_mod.scaffold(root, dry_run=True)
    assert "README.md" in statuses(results, scaffold_mod.Status.SKIPPED)
    assert (root / "README.md").read_text(encoding="utf-8") == "mine"


# --- file format ----------------------------------------------------------


def test_files_use_lf_line_endings_and_utf8(root: Path) -> None:
    scaffold_mod.scaffold(root)
    for path in root.rglob("*"):
        if path.is_file():
            data = path.read_bytes()
            assert b"\r\n" not in data, f"{path} has CRLF"
            data.decode("utf-8")


def test_manifest_has_no_duplicate_or_absolute_paths() -> None:
    dirs, files = scaffold_mod.build_manifest()
    assert len(dirs) == len(set(dirs))
    for rel in (*dirs, *files):
        assert not Path(rel).is_absolute() and ".." not in Path(rel).parts


def test_manifest_directories_are_listed_parents_first() -> None:
    dirs, _ = scaffold_mod.build_manifest()
    seen: set[str] = set()
    for d in dirs:
        parent = Path(d).parent.as_posix()
        assert parent == "." or parent in seen
        seen.add(d)


# --- command line ---------------------------------------------------------


def test_cli_prints_created_then_skipped_on_second_run(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert scaffold_mod.main(["--root", str(root)]) == 0
    first = capsys.readouterr().out
    assert "[created] src/wbms/__init__.py" in first
    assert "Skipped (already existed): 0" in first

    assert scaffold_mod.main(["--root", str(root)]) == 0
    second = capsys.readouterr().out
    assert "[skipped] README.md (already exists)" in second
    assert "[created]" not in second


def test_cli_dry_run_flag_prints_plan_and_writes_nothing(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert scaffold_mod.main(["--root", str(root), "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "DRY RUN" in out and "[would create] .env.example" in out
    assert not root.exists()


def test_cli_returns_1_on_conflict(root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root.mkdir()
    (root / "tests").write_text("a file", encoding="utf-8")
    assert scaffold_mod.main(["--root", str(root)]) == 1
    assert "[conflict] tests/" in capsys.readouterr().out


def test_cli_output_is_plain_ascii(root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    scaffold_mod.main(["--root", str(root)])
    capsys.readouterr().out.encode("ascii")  # would raise on a Windows-hostile character


def test_default_root_is_folder_above_scripts_when_inside_scripts(tmp_path: Path) -> None:
    module = _copy_script_to(tmp_path / "proj" / "scripts")
    assert module.default_root() == (tmp_path / "proj").resolve()


def test_default_root_is_none_when_not_inside_scripts_folder(tmp_path: Path) -> None:
    module = _copy_script_to(tmp_path / "proj")
    assert module.default_root() is None


def test_cli_without_root_outside_scripts_refuses_and_writes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project = tmp_path / "proj"
    module = _copy_script_to(project)
    before = sorted(p.name for p in tmp_path.rglob("*"))
    assert module.main([]) == 2
    err = capsys.readouterr().err
    assert "--root" in err
    assert sorted(p.name for p in tmp_path.rglob("*")) == before  # nothing created


def test_cli_without_root_inside_scripts_scaffolds_the_parent(tmp_path: Path) -> None:
    module = _copy_script_to(tmp_path / "proj" / "scripts")
    assert module.main([]) == 0
    assert (tmp_path / "proj" / "src" / "wbms" / "__init__.py").is_file()
    assert not (tmp_path / "src").exists()  # never leaks above the project


def test_cli_root_dot_works_when_script_is_loose(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = tmp_path / "proj"
    module = _copy_script_to(project)
    monkeypatch.chdir(project)
    assert module.main(["--root", "."]) == 0
    assert (project / "src" / "wbms" / "__init__.py").is_file()
