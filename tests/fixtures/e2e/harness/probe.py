"""Guard probe: an outside address must be refused; a loopback one must not be (run through sitecustomize)."""
import socket
import sys
import threading

ok = True
for label, fn in (
    ("create_connection 203.0.113.9:80", lambda: socket.create_connection(("203.0.113.9", 80), timeout=3)),
    ("raw connect 203.0.113.9:80", lambda: socket.socket().connect(("203.0.113.9", 80))),
    ("lookup www.example.org", lambda: socket.getaddrinfo("www.example.org", 443)),
    ("udp send 192.0.2.53:53", lambda: socket.socket(socket.AF_INET, socket.SOCK_DGRAM).sendto(b"x", ("192.0.2.53", 53))),
    # a DNS question is never local: a loopback stub resolver (127.0.0.53 on Linux runners) is the way out to the network
    ("udp send loopback stub 127.0.0.53:53", lambda: socket.socket(socket.AF_INET, socket.SOCK_DGRAM).sendto(b"x", ("127.0.0.53", 53))),
    ("tcp connect loopback stub 127.0.0.53:53", lambda: socket.create_connection(("127.0.0.53", 53), timeout=3)),
):
    try:
        fn()
        print("NOT REFUSED:", label)
        ok = False
    except OSError as e:
        print("refused:", label, "->", type(e).__name__, str(e)[:80])

srv = socket.socket()
srv.bind(("127.0.0.1", 0))
srv.listen(1)
port = srv.getsockname()[1]
threading.Thread(target=lambda: srv.accept(), daemon=True).start()
try:
    socket.create_connection(("127.0.0.1", port), timeout=3).close()
    print("loopback allowed: 127.0.0.1", port)
except OSError as e:
    print("loopback WRONGLY refused:", e)
    ok = False
sys.exit(0 if ok else 1)
