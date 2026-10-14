"""Crash-capture wrapper for the TELEMAPPER TUI.

Runs the app; on any exception inside the query handler, writes the full
traceback to telemapper_debug.log, prints a notice, and re-raises so the
UI still shows the error.
"""

import traceback

from app.telemapper import TelemapperApp


class DiagnosticApp(TelemapperApp):
    async def on_input_submitted(self, event):
        try:
            await super().on_input_submitted(event)
        except Exception:
            with open("telemapper_debug.log", "w", encoding="utf-8") as f:
                f.write(traceback.format_exc())
            print("CRASH CAPTURED to telemapper_debug.log")
            # still raise so the UI shows the error
            raise


if __name__ == '__main__':
    app = DiagnosticApp()
    app.run()
