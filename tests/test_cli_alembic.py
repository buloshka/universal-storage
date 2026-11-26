from pathlib import Path

import pytest

from storage.cli.main import init_alembic


def test_init_alembic_scaffolds_files(tmp_path: Path) -> None:
    """Verify init_alembic creates alembic.ini, env.py, script.py.mako, and versions directory."""
    init_alembic(target_dir=tmp_path, migrations_folder="migrations", force=False)

    ini_file = tmp_path / "alembic.ini"
    migrations_dir = tmp_path / "migrations"
    env_file = migrations_dir / "env.py"
    mako_file = migrations_dir / "script.py.mako"
    versions_dir = migrations_dir / "versions"

    assert ini_file.is_file()
    assert env_file.is_file()
    assert mako_file.is_file()
    assert versions_dir.is_dir()

    ini_content = ini_file.read_text(encoding="utf-8")
    assert "script_location = migrations" in ini_content

    env_content = env_file.read_text(encoding="utf-8")
    assert "from storage.adapters.sql import SQLBaseModel" in env_content


def test_init_alembic_prevents_overwrite_without_force(tmp_path: Path) -> None:
    """Verify init_alembic exits with code 1 if files already exist and force=False."""
    init_alembic(target_dir=tmp_path, migrations_folder="migrations", force=False)

    with pytest.raises(SystemExit) as exc_info:
        init_alembic(target_dir=tmp_path, migrations_folder="migrations", force=False)

    assert exc_info.value.code == 1


def test_init_alembic_overwrites_with_force(tmp_path: Path) -> None:
    """Verify init_alembic overwrites existing configuration when force=True."""
    init_alembic(target_dir=tmp_path, migrations_folder="db_migrations", force=False)
    ini_file = tmp_path / "alembic.ini"
    ini_file.write_text("corrupted content", encoding="utf-8")

    init_alembic(target_dir=tmp_path, migrations_folder="db_migrations", force=True)

    assert "script_location = db_migrations" in ini_file.read_text(encoding="utf-8")
