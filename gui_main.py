# gui_main.py
# -*- coding: utf-8 -*-
import sys
import os

# ---------------------------------------------------------
# [CRITICAL FIX] Bundle Startup Fixes
# ---------------------------------------------------------
if getattr(sys, 'frozen', False):
    bundle_dir = sys._MEIPASS
    current_dyld = os.environ.get('DYLD_LIBRARY_PATH', '')
    os.environ['DYLD_LIBRARY_PATH'] = f"{bundle_dir}{os.pathsep}{current_dyld}"
    os.environ['PATH'] = f"{bundle_dir}{os.pathsep}{os.environ.get('PATH', '')}"
    try:
        sys.stdout = open(os.devnull, "w")
        sys.stderr = open(os.devnull, "w")
    except Exception:
        pass

# PyQt6 Imports
from PyQt6.QtWidgets import QApplication
from qfluentwidgets import (
    FluentWindow, NavigationItemPosition, FluentIcon, setTheme, Theme
)

# Import Pages from Modular Files
try:
    from Code.GUI.Home import HomePage
    from Code.GUI.Results import ResultsPage
    from Code.GUI.Logs import LogPage
    from Code.GUI.Settings import SettingsPage
except ImportError as e:
    print("Critical Import Error: Ensure 'Code/GUI' directory exists with all module files.")
    print(f"Error: {e}")
    sys.exit(1)

class MainWindow(FluentWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SMT4ModPlant GUI Orchestrator")
        setTheme(Theme.DARK)
        self.resize(1100, 750)
        
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            self.move(geo.width()//2 - self.width()//2, geo.height()//2 - self.height()//2)
        
        # Initialize Pages
        # Settings needs to be created early so Home can reference it
        self.settings_page = SettingsPage(self)
        self.log_page = LogPage(self)
        self.results_page = ResultsPage(self)
        self.home_page = HomePage(self.log_callback_shim, self.settings_page, self)
        
        # Add Navigation
        self.addSubInterface(self.home_page, FluentIcon.HOME, "Home", NavigationItemPosition.TOP)
        self.addSubInterface(self.results_page, FluentIcon.ACCEPT, "Results", NavigationItemPosition.TOP)
        self.addSubInterface(self.log_page, FluentIcon.DOCUMENT, "Log", NavigationItemPosition.TOP)
        self.addSubInterface(self.settings_page, FluentIcon.SETTING, "Settings", NavigationItemPosition.BOTTOM)
        
        self.switchTo(self.home_page)

    def log_callback_shim(self, msg):
        self.log_page.append_log(msg)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())