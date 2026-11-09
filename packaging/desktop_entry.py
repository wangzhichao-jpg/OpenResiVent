"""PyInstaller 命令入口。"""

from openresivent.cli import app

if __name__ == "__main__":
    import multiprocessing

    multiprocessing.freeze_support()
    app()
