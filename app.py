import sys
from ui.main_window import MovieUpdaterWindow

if __name__ == "__main__":
    auto = "--auto" in sys.argv
    app = MovieUpdaterWindow(auto_mode=auto)
    app.mainloop()
