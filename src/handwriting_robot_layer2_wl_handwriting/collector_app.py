from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .charset import default_charset_path, load_target_charset
from .storage import SampleStore


def build_parser() -> argparse.ArgumentParser:
    repository_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description="Personal handwriting tablet collector")
    parser.add_argument("--charset", type=Path, default=default_charset_path())
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=repository_root / "runtime_data" / "handwriting",
    )
    parser.add_argument("--writer-id", default="")
    parser.add_argument("--writer-name", default="")
    return parser


def run(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        from PySide6.QtWidgets import QApplication, QDialog, QMessageBox
    except ImportError:
        print(
            "PySide6 is not installed. Run: py -3 -m pip install -r "
            "src/handwriting_robot_layer2_wl_handwriting/requirements.txt",
            file=sys.stderr,
        )
        return 2

    from .collector_ui import MainWindow, WriterDialog

    app = QApplication(sys.argv[:1])
    app.setApplicationName("个人笔迹采集")

    try:
        entries = load_target_charset(args.charset)
    except (OSError, ValueError) as error:
        QMessageBox.critical(None, "字符集读取失败", str(error))
        return 1

    writer_id = args.writer_id.strip()
    writer_name = args.writer_name.strip()
    if not writer_id:
        dialog = WriterDialog()
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return 0
        writer_id = dialog.writer_id.text().strip()
        writer_name = dialog.writer_name.text().strip()

    try:
        store = SampleStore(args.data_dir, writer_id, writer_name)
    except (OSError, ValueError) as error:
        QMessageBox.critical(None, "书写者档案创建失败", str(error))
        return 1

    window = MainWindow(entries, store, args.charset)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(run())
