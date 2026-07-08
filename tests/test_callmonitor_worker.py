import socket
import threading
import time

from fritz_callhistory.fritz.callmonitor import CallMonitorConnection
from fritz_callhistory.gui.callmonitor_worker import CallMonitorThread


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _serve_once(port: int, lines: list[str]) -> socket.socket:
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", port))
    server.listen(1)

    def serve():
        conn, _ = server.accept()
        with conn:
            for line in lines:
                conn.sendall((line + "\n").encode())
            conn.recv(1)  # blockiert, bis die Gegenseite die Verbindung schließt

    threading.Thread(target=serve, daemon=True).start()
    return server


def test_call_monitor_thread_emits_ring_event(qtbot):
    port = _free_port()
    server = _serve_once(port, ["01.01.26 20:00:00;RING;0;030123456;069987654;SIP0;"])

    worker = CallMonitorThread("127.0.0.1", port=port, reconnect_delay_seconds=0.05)
    try:
        with qtbot.waitSignal(worker.ring, timeout=3000) as blocker:
            worker.start()
        assert blocker.args == ["0", "030123456", "069987654"]
    finally:
        worker.stop()
        worker.wait(2000)
        server.close()


def test_call_monitor_thread_emits_connected_and_disconnected(qtbot):
    port = _free_port()
    server = _serve_once(
        port,
        [
            "01.01.26 20:00:00;RING;5;030123456;069987654;SIP0;",
            "28.11.20 15:17:47;CONNECT;5;4;030123456;",
            "28.11.20 15:17:50;DISCONNECT;5;4;",
        ],
    )

    worker = CallMonitorThread("127.0.0.1", port=port, reconnect_delay_seconds=0.05)
    try:
        with qtbot.waitSignal(worker.disconnected, timeout=3000) as disconnect_blocker:
            with qtbot.waitSignal(worker.connected, timeout=3000) as connect_blocker:
                worker.start()
        assert connect_blocker.args == ["5"]
        assert disconnect_blocker.args == ["5"]
    finally:
        worker.stop()
        worker.wait(2000)
        server.close()


def test_call_monitor_thread_emits_connection_lost_when_unreachable(qtbot):
    unreachable_port = _free_port()  # niemand lauscht dort

    worker = CallMonitorThread("127.0.0.1", port=unreachable_port, reconnect_delay_seconds=0.05)
    try:
        with qtbot.waitSignal(worker.connection_lost, timeout=3000):
            worker.start()
    finally:
        worker.stop()
        worker.wait(2000)


def test_call_monitor_thread_stop_during_connect_does_not_hang(qtbot, monkeypatch):
    # Regression test: stop() called while connect() is still in-flight used to race,
    # since close() on the not-yet-connected CallMonitorConnection was a no-op, leaving
    # the worker stuck in a blocking recv() forever (never caught by wait(2000)).
    port = _free_port()
    server = _serve_once(port, ["01.01.26 20:00:00;RING;0;030123456;069987654;SIP0;"])

    original_connect = CallMonitorConnection.connect

    def delayed_connect(self):
        time.sleep(0.2)
        original_connect(self)

    monkeypatch.setattr(CallMonitorConnection, "connect", delayed_connect)

    worker = CallMonitorThread("127.0.0.1", port=port, reconnect_delay_seconds=0.05)
    try:
        worker.start()
        time.sleep(0.05)  # worker is inside connect()'s artificial delay now
        worker.stop()
        assert worker.wait(2000), "worker did not stop within timeout"
    finally:
        server.close()


def test_call_monitor_thread_stop_while_idle_in_recv_does_not_hang(qtbot):
    # Regression test: stop() called while the worker is connected and blocked
    # in recv() waiting for the *next* line (no data pending, the normal idle
    # state between calls) used to occasionally not unblock in time, since
    # close() relied purely on shutdown()'s cross-thread recv()-wakeup timing.
    port = _free_port()
    server = _serve_once(port, [])  # akzeptiert, sendet nichts, haelt offen

    worker = CallMonitorThread("127.0.0.1", port=port, reconnect_delay_seconds=0.05)
    try:
        worker.start()
        time.sleep(0.1)  # worker ist jetzt verbunden und blockiert in recv()
        worker.stop()
        assert worker.wait(2000), "worker did not stop within timeout"
    finally:
        server.close()


def test_call_monitor_thread_stop_during_reconnect_delay_does_not_hang(qtbot):
    # Regression test: the reconnect backoff used to be a plain time.sleep(),
    # which stop() could not interrupt - the worker would keep sleeping for up
    # to reconnect_delay_seconds regardless of stop() having been called.
    unreachable_port = _free_port()

    worker = CallMonitorThread(
        "127.0.0.1", port=unreachable_port, reconnect_delay_seconds=5.0
    )
    with qtbot.waitSignal(worker.connection_lost, timeout=3000):
        worker.start()
    time.sleep(0.05)  # worker is now inside the 5s reconnect wait
    worker.stop()
    assert worker.wait(2000), "worker did not stop within timeout"


def test_call_monitor_thread_ignores_non_ring_events(qtbot):
    port = _free_port()
    server = _serve_once(
        port,
        [
            "01.01.26 20:00:05;CALL;0;1;069987654;030123456;SIP0;",
            "01.01.26 20:00:00;RING;0;030123456;069987654;SIP0;",
        ],
    )

    worker = CallMonitorThread("127.0.0.1", port=port, reconnect_delay_seconds=0.05)
    try:
        with qtbot.waitSignal(worker.ring, timeout=3000) as blocker:
            worker.start()
        # Das CALL-Ereignis wurde übersprungen, nur das folgende RING kam an.
        assert blocker.args == ["0", "030123456", "069987654"]
    finally:
        worker.stop()
        worker.wait(2000)
        server.close()
