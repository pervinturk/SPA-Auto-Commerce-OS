import multiprocessing
import sys


def main():
    from ui.main_window import MainWindow
    app = MainWindow()
    app.mainloop()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
