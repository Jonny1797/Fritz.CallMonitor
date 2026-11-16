"""Einstiegspunkt: QApplication starten und MainWindow anzeigen."""

from __future__ import annotations

import os
import signal
import sys

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication, QDialog

from fritz_callhistory import config as config_module
from fritz_callhistory.db.connection import connect
from fritz_callhistory.gui.background_tasks import BackgroundTasks
from fritz_callhistory.gui.credentials_dialog import CredentialsDialog
from fritz_callhistory.gui.icon import app_icon
from fritz_callhistory.gui.main_window import MainWindow
from fritz_callhistory.paths import database_file
from fritz_callhistory.sync.box_gateway import BoxGateway


def _handle_sigint(*_args) -> None:
    """Strg+C beendet den Prozess sofort und hart, statt über window.close()
    zu gehen: MainWindow.closeEvent() wartet bei einem normalen Schliessen
    bewusst auf noch laufende Hintergrundaufgaben (Sync, Box-Import) - das
    ist für einen Klick auf X das richtige Verhalten, aber für Strg+C
    erwartet man in einem Terminal-Programm einen sofortigen Abbruch, egal was
    gerade läuft (z.B. ein Netzwerkaufruf, der trotz Timeout in
    fritz/client.py hängt, etwa durch einen blockierenden DNS-Lookup, den
    requests' timeout-Parameter nicht abdeckt). os._exit() umgeht Qt's/Pythons
    normale Aufräum-Reihenfolge komplett - kein qFatal-Crash-Risiko durch noch
    laufende QThreads, da deren Destruktoren gar nicht erst aufgerufen werden;
    das Betriebssystem räumt Sockets/Dateien beim Prozessende ohnehin auf, und
    jeder DB-Schreibzugriff committet bereits einzeln (siehe db/repository.py),
    es geht also höchstens ein einzelner, gerade laufender Schreibzugriff
    verloren."""
    os._exit(130)  # 128 + SIGINT, übliche Exitcode-Konvention


def _run_first_start_dialog(cfg, gateway: BoxGateway):
    """Zugangsdaten-Dialog vor dem Hauptfenster, mit eigener kurzlebiger BackgroundTasks-Instanz."""
    tasks = BackgroundTasks()
    dialog = CredentialsDialog(cfg, tasks, gateway)
    if dialog.exec() == QDialog.DialogCode.Accepted:
        cfg = dialog.save(cfg)
    if not tasks.is_idle():
        # Abbruch während der Prüfung: den laufenden Thread zu Ende laufen lassen,
        # bevor die Instanz verworfen wird (sonst "QThread destroyed while running").
        # Bewusst kein begin_quit(): dessen Failsafe würde die App per os._exit()
        # beenden, wenn die Prüfung länger als der Failsafe dauert (Request-Timeout
        # ist länger) - der Nutzer will aber ohne Zugangsdaten weitermachen. Das
        # späte Ergebnis verwirft der geschlossene Dialog selbst (siehe done()).
        loop = QEventLoop()
        tasks.all_finished.connect(loop.quit)
        loop.exec()
    return cfg


def main() -> int:
    app = QApplication(sys.argv)
    app.setWindowIcon(app_icon())
    # Muss unabhängig vom Minimize-to-Tray-Setting explizit False sein: sonst
    # könnte Qt beim Verstecken des einzigen Top-Level-Fensters implizit
    # beenden, was closeEvent()'s eigene Minimize-vs-Quit-Entscheidung
    # untergraben würde (siehe MainWindow.closeEvent()).
    app.setQuitOnLastWindowClosed(False)
    connection = connect(database_file())
    cfg = config_module.load()
    gateway = BoxGateway(cfg, db_path=database_file())

    if not gateway.has_credentials:
        cfg = _run_first_start_dialog(cfg, gateway)
        gateway.apply_config(cfg)

    window = MainWindow(connection, cfg, gateway)
    window.show()

    # Qt's C++-Eventloop liefert SIGINT erst, wenn wieder Python-Bytecode
    # läuft; der No-Op-Timer sorgt dafür, dass das zeitnah passiert statt
    # erst bei der nächsten GUI-Interaktion (siehe _handle_sigint()).
    signal.signal(signal.SIGINT, _handle_sigint)
    signal_timer = QTimer()
    signal_timer.timeout.connect(lambda: None)
    signal_timer.start(200)

    exit_code = app.exec()
    # os._exit() statt return: sobald app.exec() zurückkehrt (regulär über
    # MainWindow.closeEvent()'s expliziten QApplication.quit()-Aufruf, oder
    # über quitOnLastWindowClosed), soll der Prozess sofort enden - nicht
    # über Pythons normale Interpreter-Shutdown-Sequenz, in der PySide beim
    # atexit-Handling alle verbliebenen QObjects zerstört (inkl. etwaiger
    # noch lebender QThreads, was den ursprünglichen "QThread: Destroyed
    # while thread ... is still running"-SIGABRT auslöst). Jeder
    # DB-Schreibzugriff committet bereits einzeln (siehe db/repository.py),
    # ein abgebrochener Shutdown verliert also höchstens einen einzelnen,
    # gerade laufenden Schreibzugriff.
    os._exit(exit_code)


if __name__ == "__main__":
    raise SystemExit(main())
