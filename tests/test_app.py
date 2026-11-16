from fritz_callhistory.app import _handle_sigint


def test_sigint_handler_forces_immediate_exit_unconditionally(mocker):
    # Regression test: SIGINT used to route through window.close(), which
    # MainWindow.closeEvent() can defer indefinitely while a worker thread is
    # busy (correct for a normal window close, but not what Ctrl+C in a
    # terminal is expected to do). The handler must force an immediate exit
    # instead, with no dependency on any window/thread state.
    force_exit = mocker.patch("fritz_callhistory.app.os._exit")

    _handle_sigint()

    force_exit.assert_called_once_with(130)


def test_first_start_cancel_during_slow_check_waits_without_forced_exit(qtbot, mocker):
    # Abbruch während einer langsamen Prüfung beim ersten Start: Es wird auf die
    # laufende Prüfung gewartet, aber die App darf dabei nicht per Failsafe
    # (os._exit) beendet werden - der Nutzer will ja ohne Zugangsdaten weiter.
    import threading

    from PySide6.QtWidgets import QDialog

    from fritz_callhistory import app as app_module
    from fritz_callhistory.config import Config
    from fritz_callhistory.gui.background_tasks import BackgroundTasks

    exits = []
    created = []

    def tasks_factory():
        tasks = BackgroundTasks(exit_fn=lambda: exits.append(1), failsafe_timeout_s=0.05)
        created.append(tasks)
        return tasks

    release = threading.Event()

    class SlowCheckDialog:
        def __init__(self, cfg, tasks, gateway):
            self._tasks = tasks

        def exec(self):
            from PySide6.QtCore import QObject

            self._context = QObject()
            self._tasks.start(
                lambda: release.wait(5), self._context, lambda _r: None, lambda _e: None
            )
            # Prüfung läuft länger als der Failsafe; Nutzer bricht sofort ab.
            threading.Timer(0.3, release.set).start()
            return QDialog.DialogCode.Rejected

    mocker.patch.object(app_module, "BackgroundTasks", side_effect=tasks_factory)
    mocker.patch.object(app_module, "CredentialsDialog", SlowCheckDialog)

    cfg = Config()
    assert app_module._run_first_start_dialog(cfg, gateway=None) is cfg

    assert created[0].is_idle()
    assert exits == []
