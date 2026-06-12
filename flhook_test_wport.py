import socket
import time

host = "127.0.0.1"
port = 1920
password = "test"


def recv_text(sock, timeout=2.0):
    sock.settimeout(0.25)
    chunks = []
    end_time = time.time() + timeout

    while time.time() < end_time:
        try:
            data = sock.recv(65535)
            if not data:
                break
            chunks.append(data)
        except socket.timeout:
            pass

    raw = b"".join(chunks)
    if not raw:
        return ""

    try:
        return raw.decode("utf-16le", errors="ignore").replace("\x00", "")
    except Exception:
        return raw.decode("latin1", errors="ignore").replace("\x00", "")


def send_cmd(sock, cmd):
    if not cmd.endswith("\n"):
        cmd += "\n"
    sock.sendall(cmd.encode("utf-16le"))


with socket.create_connection((host, port), timeout=5) as sock:
    print("connected")

    welcome = recv_text(sock, timeout=2)
    print("welcome:")
    print(welcome)

    send_cmd(sock, f"pass {password}")
    auth = recv_text(sock, timeout=2)
    print("auth:")
    print(auth)

    send_cmd(sock, "help")
    result = recv_text(sock, timeout=3)
    print("help:")
    print(result)

    send_cmd(sock, "quit")
    bye = recv_text(sock, timeout=1)
    print("quit:")
    print(bye)