"""模块入口：python -m file_organizer。"""

from .utils import report_missing_gui_dependency


def main() -> None:
    try:
        from .app import main as run
    except ModuleNotFoundError as exc:
        if report_missing_gui_dependency(exc):
            raise SystemExit(1) from None
        raise
    run()


if __name__ == "__main__":
    main()
