#!/usr/bin/env python3
"""Railway launcher: one dual-stack socket on [::]:$PORT (IPv4 + IPv6).

Railway private networking (*.railway.internal) needs IPv6; public/health traffic may be IPv4.
uvicorn --host :: is IPv6-only, so bind the socket ourselves with IPV6_V6ONLY=0.
"""
import os, socket, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import uvicorn

port = int(os.getenv("PORT") or os.getenv("MEMORY_PORT") or 8092)
sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
sock.bind(("::", port))
print(f"[serve] dual-stack listen [::]:{port}", flush=True)
uvicorn.Server(uvicorn.Config("app.main:app", log_level="info")).run(sockets=[sock])
