import socket
import threading

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
