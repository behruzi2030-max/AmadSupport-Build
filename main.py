"""Bootstrap launcher for AmadSupport.

Installs a very early crash handler, then runs the real application
(app_main.py). If anything fails while importing or starting the app,
the full traceback is shown on screen (and saved to crash.log) instead
of the app silently dying right after the Android loading splash.
"""
import os
import sys
import time
import traceback
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
CRASH_LOG = APP_DIR / 'crash.log'


def _format_exc():
    return ''.join(traceback.format_exception(*sys.exc_info()))


def _log(text):
    try:
        with open(CRASH_LOG, 'a', encoding='utf-8') as fh:
            fh.write('\n' + time.strftime('%Y-%m-%d %H:%M:%S') + '\n' + text)
    except Exception:
        pass


def _show_error(text):
    """Draw the error on a Kivy window and keep the app alive."""
    try:
        from kivy.core.window import Window
        from kivy.uix.label import Label
        from kivy.uix.scrollview import ScrollView
        from kivy.base import runTouchApp

        Window.clearcolor = (0.07, 0.07, 0.08, 1)
        text = text if len(text) < 5000 else text[-5000:]

        lb = Label(text=text, font_name='Roboto', font_size='10sp',
                   halign='left', valign='top', size_hint_y=None,
                   color=(1, 0.4, 0.4, 1), padding=(10, 10))
        lb.bind(width=lambda i, v: setattr(lb, 'text_size', (v, None)))
        lb.bind(texture_size=lambda i, v: setattr(lb, 'height', v[1]))
        sv = ScrollView(size=Window.size)
        sv.add_widget(lb)
        runTouchApp(sv)          # keeps the window open until user kills it
    except Exception:
        # last resort: log + pause so it does not loop-crash
        _log(text)
        while True:
            time.sleep(5)


def _excepthook(etype, value, tb):
    sys.__excepthook__(etype, value, tb)
    text = ''.join(traceback.format_exception(etype, value, tb))
    _log(text)
    _show_error(text)


sys.excepthook = _excepthook

try:
    from kivy.base import ExceptionManager

    def _em_handler(exc):
        text = _format_exc()
        _log(text)
        _show_error(text)
        raise exc

    ExceptionManager.add_handler(_em_handler)
except Exception:
    pass

# ---------------------------------------------------------------
# actual application start
# ---------------------------------------------------------------
try:
    sys.path.insert(0, str(APP_DIR))
    import app_main  # noqa: E402  (registers fonts, data dirs, crash log)
    app_main.run_app()
except BaseException:
    text = _format_exc()
    _log(text)
    _show_error(text)
    while True:
        time.sleep(5)
