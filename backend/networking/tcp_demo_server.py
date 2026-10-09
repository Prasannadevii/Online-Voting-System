"""EDUCATIONAL raw-TCP voting protocol (NOT used by the web app for authentication).

CN CONCEPTS: socket() bind() listen() accept() recv() send() close(); one thread per
connection; application-layer protocol; MESSAGE FRAMING.

TCP is a reliable, ordered BYTE STREAM - it has no message boundaries. Two send() calls
may arrive in one recv(), and one send() may arrive in several recv() calls. So recv(1024)
alone is not a protocol. We prefix each message with a 4-byte big-endian length:

    [ 4-byte length N ][ N bytes of UTF-8 text ]      e.g.  00 00 00 0A | HELLO|C001

Protocol:  HELLO|id -> WELCOME|id   AUTH|voter|pw -> AUTH_OK/AUTH_FAIL
           VOTE|candidate|REQ -> VOTE_ACK|TX   QUIT -> BYE

Standalone:  python -m backend.networking.tcp_demo_server --port 9000
"""
import argparse
import os
import socket
import struct
import threading

from werkzeug.security import check_password_hash

MAX_FRAME = 4096


def send_msg(sock: socket.socket, text: str) -> bytes:
    payload = text.encode("utf-8")
    frame = struct.pack("!I", len(payload)) + payload
    sock.sendall(frame)                        # sendall loops until every byte is queued
    return frame


def recv_exact(sock: socket.socket, n: int) -> bytes:
    """recv() may return FEWER bytes than asked; loop until we have exactly n."""
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("peer closed the connection")
        buf += chunk
    return buf


def recv_msg(sock: socket.socket):
    header = recv_exact(sock, 4)
    (length,) = struct.unpack("!I", header)
    if length > MAX_FRAME:                      # protects memory from a hostile length value
        raise ValueError(f"frame too large ({length})")
    return recv_exact(sock, length).decode("utf-8"), header


class TCPDemoServer:
    def __init__(self, handler_ctx, host="127.0.0.1", port=0):
        """handler_ctx: object with .authenticate(voter, pw) -> bool and .vote(voter, cand, req) -> tx."""
        self.ctx, self.host = handler_ctx, host
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)         # socket()
        if os.name == "nt":      # Windows: SO_REUSEADDR would allow two servers on one port
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        else:                    # POSIX: lets the server restart immediately (TIME_WAIT sockets)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((host, port))                                          # bind()
        self.port = self.sock.getsockname()[1]
        self.sock.listen(5)                                                   # listen()
        self.running, self.thread, self.clients = True, None, []

    def start(self):
        self.thread = threading.Thread(target=self._accept_loop, name="tcp-accept", daemon=True)
        self.thread.start()
        return self

    def _accept_loop(self):
        self.sock.settimeout(0.5)
        while self.running:
            try:
                conn, addr = self.sock.accept()                               # accept()
            except socket.timeout:
                continue
            except OSError:
                break
            t = threading.Thread(target=self._serve, args=(conn, addr), daemon=True)
            self.clients.append(t)
            t.start()

    def _serve(self, conn, addr):
        conn.settimeout(10)                    # TIMEOUT: never wait forever on a silent client
        user = None
        try:
            while True:
                text, _ = recv_msg(conn)
                parts = text.split("|")
                cmd = parts[0].upper()
                if cmd == "HELLO" and len(parts) == 2:
                    send_msg(conn, f"WELCOME|{parts[1]}")
                elif cmd == "AUTH" and len(parts) == 3:
                    if self.ctx.authenticate(parts[1], parts[2]):
                        user = parts[1]; send_msg(conn, "AUTH_OK")
                    else:
                        send_msg(conn, "AUTH_FAIL")
                elif cmd == "VOTE" and len(parts) == 3:
                    if not user:
                        send_msg(conn, "ERROR|NOT_AUTHENTICATED")
                    else:
                        ok, info = self.ctx.vote(user, parts[1], parts[2])
                        send_msg(conn, f"VOTE_ACK|{info}" if ok else f"ERROR|{info}")
                elif cmd == "QUIT":
                    send_msg(conn, "BYE")
                    break
                else:
                    send_msg(conn, "ERROR|UNKNOWN_COMMAND")
        except (ConnectionError, socket.timeout, ValueError, OSError):
            pass
        finally:
            conn.close()                                                      # close()

    def stop(self):
        self.running = False
        try:
            self.sock.close()
        except OSError:
            pass
        if self.thread:
            self.thread.join(2)


class DemoContext:
    """Bridges the TCP protocol to an isolated demo database."""

    def __init__(self, db_path, password_hash, lock, secret):
        self.db_path, self.pw_hash, self.lock, self.secret = db_path, password_hash, lock, secret

    def authenticate(self, voter, pw):
        return voter == "D0001" and check_password_hash(self.pw_hash, pw)

    def vote(self, voter, candidate, req):
        from backend.services import voting_service
        try:
            r = voting_service.cast_vote(self.db_path, voter, int(candidate), req, "127.0.0.1", "tcp-demo",
                                         lock=self.lock, ref_secret=self.secret, audit=False)
            return True, r["transaction_id"]
        except voting_service.VoteError as exc:
            return False, exc.code
        except ValueError:
            return False, "INVALID_CANDIDATE"


def main():
    import os
    from backend.concurrency.race_demo import DEMO_SECRET, cleanup, make_demo_db
    from backend.concurrency.vote_lock import InstrumentedLock
    from backend.security.hashing import hash_password
    ap = argparse.ArgumentParser(description="NetVote educational TCP server")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=9000)
    a = ap.parse_args()
    folder, path = make_demo_db(True, 1)
    srv = TCPDemoServer(DemoContext(path, hash_password("demo-pass", 1000), InstrumentedLock(), DEMO_SECRET),
                        a.host, a.port).start()
    print(f"TCP demo server on {a.host}:{srv.port} - demo login AUTH|D0001|demo-pass  (Ctrl+C to stop)")
    try:
        while True:
            threading.Event().wait(1)
    except KeyboardInterrupt:
        pass
    finally:
        srv.stop(); cleanup(folder)


if __name__ == "__main__":
    main()
