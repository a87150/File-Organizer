"""图形界面启动入口：python run.py。"""

from file_organizer.utils import report_missing_gui_dependency


def main() -> None:
    try:
        from file_organizer.app import main as run
    except ModuleNotFoundError as exc:
        if report_missing_gui_dependency(exc):
            raise SystemExit(1) from None
        raise
    run()


if __name__ == "__main__":
    main()
