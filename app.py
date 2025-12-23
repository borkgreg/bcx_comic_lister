#!/usr/bin/env python3
import sys


def main():
    # IMPORTANT:
    # - Main GUI (Tk) runs in one process
    # - CLZ Scraper (Qt) runs in a separate process
    # This flag makes the *same bundled binary* run scraper-only.
    if "--run-clz-scraper" in sys.argv:
        # Do NOT import tkinter anywhere on this path.
        from tools.clz_scraper.app import main as scraper_main
        scraper_main()
        return

    # Do NOT import PyQt anywhere on this path.
    from gui.main_window import BCXMainWindow
    BCXMainWindow().run()


if __name__ == "__main__":
    main()