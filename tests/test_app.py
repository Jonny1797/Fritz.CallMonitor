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
