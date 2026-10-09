"""EDUCATIONAL raw-TCP client + scripted session used by the TCP Demo page.

Standalone:  python -m backend.networking.tcp_demo_client --port 9000
"""
import argparse
import socket
import threading
import time

from backend.networking.tcp_demo_server import (DemoContext, TCPDemoServer, recv_msg, send_msg)


def run_session(host, port, script):
    """Run commands against a server; returns a transcript with the raw frame bytes."""
    transcript = []
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)                    # socket()
    s.settimeout(5)
    s.connect((host, port))                                                  # connect() -> TCP 3-way handshake
    transcript.append({"dir": "info", "text": f"connect() to {host}:{port} - TCP handshake complete "
                                              f"(local port {s.getsockname()[1]})", "hex": ""})
    try:
        for cmd in script:
            frame = send_msg(s, cmd)                                          # send()
            transcript.append({"dir": "client", "text": cmd, "hex": frame.hex(" ")})
            reply, _ = recv_msg(s)                                            # recv()
            transcript.append({"dir": "server", "text": reply, "hex": ""})
    finally:
        s.close()                                                            # close()
    return transcript


def framing_experiment():
    """Show WHY framing is needed: two send() calls, one recv()."""
    srv = socket.socket(); srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0)); srv.listen(1)
    port = srv.getsockname()[1]

    def serve():
        c, _ = srv.accept()
        c.sendall(b"VOTE_ACK|TX-1;")          # message 1
        c.sendall(b"VOTE_ACK|TX-2;")          # message 2 (separate send call)
        time.sleep(0.5); c.close()

    threading.Thread(target=serve, daemon=True).start()
    cl = socket.create_connection(("127.0.0.1", port), timeout=3)
    time.sleep(0.2)                           # let both segments reach the receive buffer
    chunk = cl.recv(1024)                     # ONE recv for TWO sends
    cl.close(); srv.close()
    return {"sends": 2, "recvs": 1, "received": chunk.decode(),
            "merged": chunk.count(b";") > 1,
            "lesson": "Two send() calls were delivered by ONE recv(): TCP preserves byte ORDER, not message "
                      "BOUNDARIES. Without framing the receiver cannot tell where one message ends."}


def run_full_demo(db_path, lock, secret, pw_hash):
    srv = TCPDemoServer(DemoContext(db_path, pw_hash, lock, secret), "127.0.0.1", 0).start()
    try:
        script = ["HELLO|CLIENT001", "AUTH|D0001|demo-pass", "VOTE|1|REQ-2026-TCPDEMO1",
                  "VOTE|1|REQ-2026-TCPDEMO2", "QUIT"]
        transcript = run_session("127.0.0.1", srv.port, script)
    finally:
        srv.stop()
    return {"port": srv.port, "transcript": transcript, "framing": framing_experiment(),
            "calls": ["socket()", "bind()", "listen()", "accept()", "connect()", "send()", "recv()", "close()"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=9000)
    a = ap.parse_args()
    for line in run_session(a.host, a.port, ["HELLO|CLIENT001", "AUTH|D0001|demo-pass",
                                             "VOTE|1|REQ-2026-CLI00001", "QUIT"]):
        print(f"{line['dir']:>7}: {line['text']}")


if __name__ == "__main__":
    main()
