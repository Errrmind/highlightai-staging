#!/usr/bin/env python3
"""Railway launcher: one dual-stack socket on [::]:$PORT (IPv4 + IPv6).

Railway private networking (*.railway.internal) needs IPv6; public/health traffic may be IPv4.
uvicorn --host :: is IPv6-only, so bind the socket ourselves with IPV6_V6ONLY=0.
"""
import os, socket, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import uvicorn


def _drop_privileges() -> None:
    """RW-1: if started as root (Railway default; volume is root-owned), chown the data
    dir to 'app' and permanently drop to that user before importing/serving the app.
    Works whether started via Dockerfile CMD or a Railway start command (which replaces ENTRYPOINT)."""
    if os.name != "posix" or os.geteuid() != 0:
        return
    import pwd

    try:
        pw = pwd.getpwnam(os.getenv("MEMORY_RUN_USER", "app"))
    except KeyError:
        print("[serve] WARNING: user 'app' missing; running as root", flush=True)
        return
    data = Path(os.getenv("HIGHLIGHTAI_ROOT", "/data"))
    data.mkdir(parents=True, exist_ok=True)
    for root, dirs, files in os.walk(data):
        for n in [root] + [os.path.join(root, x) for x in dirs + files]:
            try:
                os.lchown(n, pw.pw_uid, pw.pw_gid)
            except OSError:
                pass
    os.setgroups([])
    os.setgid(pw.pw_gid)
    os.setuid(pw.pw_uid)
    if os.getuid() == 0 or os.geteuid() == 0:
        raise SystemExit("[serve] failed to drop root")
    os.environ["HOME"] = "/tmp"
    print(f"[serve] dropped privileges to {pw.pw_name} ({pw.pw_uid})", flush=True)


_drop_privileges()

port = int(os.getenv("PORT") or os.getenv("MEMORY_PORT") or 8092)
sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
sock.bind(("::", port))
print(f"[serve] dual-stack listen [::]:{port}", flush=True)
uvicorn.Server(uvicorn.Config("app.main:app", log_level="info")).run(sockets=[sock])
