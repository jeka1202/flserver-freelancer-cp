import socket
import time

host = "127.0.0.1"
port = 1920
password = "test"  # сюда свой pass0 из flhook.ini / flhook.cfg


def recv_text(sock, timeout=2.0):
    sock.settimeout(0.2)
    chunks = []
    end = time.time() + timeout

    while time.time() < end:
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

    return raw.decode("utf-16le", errors="ignore").replace("\x00", "")


def send_cmd(sock, cmd, timeout=2.0):
    print(f"\n>>> {cmd}")
    sock.sendall((cmd + "\n").encode("utf-16le"))
    time.sleep(0.2)
    answer = recv_text(sock, timeout=timeout)
    print(answer)
    return answer


with socket.create_connection((host, port), timeout=5) as sock:
    print("connected")

    welcome = recv_text(sock, timeout=2)
    print("welcome:")
    print(welcome)

    auth = send_cmd(sock, f"pass {password}", timeout=2)

    if "ok" not in auth.lower():
        print("auth failed")
    else:
        players = send_cmd(sock, "getplayers", timeout=3)

    send_cmd(sock, "quit", timeout=1)