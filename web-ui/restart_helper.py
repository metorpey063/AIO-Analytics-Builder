"""Starts a fresh AIO Web UI server after the old one exits (the sidebar Restart button and Update).

Run by app._schedule_restart() as a detached process with stdout/stderr on aio_launcher.log:
    restart_helper.py <old pid> <port> <python> <app argv...>
Waits for the old process to exit and the port to be free, then replaces itself with the server.
"""
import os
import socket
import sys
import time


def log(msg):
    print(f"[restart {time.strftime('%H:%M:%S')}] {msg}", flush=True)


def pid_alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def port_free(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def main():
    old_pid, port, python, argv = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3], sys.argv[4:]
    log(f"waiting for the old server (pid {old_pid}) to exit")
    deadline = time.time() + 20
    while pid_alive(old_pid) and time.time() < deadline:
        time.sleep(0.2)
    if pid_alive(old_pid):
        log(f"old server still running after 20s; not starting a second one. Relaunch AIO Builder.")
        sys.exit(1)
    deadline = time.time() + 20
    while not port_free(port) and time.time() < deadline:
        time.sleep(0.5)
    if not port_free(port):
        log(f"port {port} is still in use after 20s (another process holds it). Relaunch AIO Builder.")
        sys.exit(1)
    log(f"starting {python} {' '.join(argv)}")
    try:
        os.execv(python, [python, *argv])
    except OSError as e:
        log(f"couldn't start the server: {e}. Relaunch AIO Builder.")
        sys.exit(1)


if __name__ == "__main__":
    main()
