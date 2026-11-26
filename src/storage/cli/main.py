import argparse
import sys
from importlib import resources
from pathlib import Path


def init_alembic(target_dir: Path, migrations_folder: str, force: bool) -> None:
    """Scaffold an async Alembic migration environment into the target project directory."""
    migrations_dir = target_dir / migrations_folder
    versions_dir = migrations_dir / "versions"
    ini_path = target_dir / "alembic.ini"

    if not force and (migrations_dir.exists() or ini_path.exists()):
        print(
            f"Error: '{migrations_folder}/' or 'alembic.ini' already exists in {target_dir}. "
            "Use --force to overwrite.",
            file=sys.stderr,
        )
        sys.exit(1)

    versions_dir.mkdir(parents=True, exist_ok=True)
    (versions_dir / ".gitkeep").touch(exist_ok=True)

    template_pkg = resources.files("storage.adapters.sql.templates")

    ini_content = template_pkg.joinpath("alembic.ini.tpl").read_text(encoding="utf-8")
    ini_content = ini_content.replace("script_location = migrations", f"script_location = {migrations_folder}")
    ini_path.write_text(ini_content, encoding="utf-8")

    env_content = template_pkg.joinpath("env.py.tpl").read_text(encoding="utf-8")
    (migrations_dir / "env.py").write_text(env_content, encoding="utf-8")

    mako_content = template_pkg.joinpath("script.py.mako").read_text(encoding="utf-8")
    (migrations_dir / "script.py.mako").write_text(mako_content, encoding="utf-8")

    print(f"Successfully initialized async Alembic environment in '{target_dir}':")
    print(f"  - {ini_path.name}")
    print(f"  - {migrations_folder}/env.py")
    print(f"  - {migrations_folder}/script.py.mako")
    print(f"  - {migrations_folder}/versions/")
    print("\nNext steps:")
    print(f"  1. Import your SQLBaseModel subclasses inside '{migrations_folder}/env.py'.")
    print("  2. Set SQL_DSN in your environment or update sqlalchemy.url in alembic.ini.")
    print('  3. Run: uv run alembic revision --autogenerate -m "initial"')
    print("  4. Run: uv run alembic upgrade head")


def cli_entrypoint() -> None:
    """CLI entry point for scaffolding Alembic migrations."""
    parser = argparse.ArgumentParser(
        prog="storage-init-alembic",
        description="Initialize an async Alembic migration environment preconfigured for universal-storage.",
    )
    parser.add_argument(
        "--path",
        type=Path,
        default=Path.cwd(),
        help="Target project root directory (defaults to current working directory).",
    )
    parser.add_argument(
        "--dir",
        type=str,
        default="migrations",
        help="Name of the migrations directory (defaults to 'migrations').",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing alembic.ini and migrations files if they exist.",
    )

    args = parser.parse_args()
    init_alembic(target_dir=args.path.resolve(), migrations_folder=args.dir, force=args.force)


if __name__ == "__main__":
    cli_entrypoint()
