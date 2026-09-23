#!/usr/bin/env python3
import socket
for name,port in (("router",8080),("parser",8081),("forwarder",8082)):
    try:
        with socket.create_connection(("127.0.0.1",port),3): print(f"PASS {name}:{port}")
    except OSError as e: print(f"FAIL {name}:{port} {e}")
