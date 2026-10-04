# SPDX-License-Identifier: AGPL-3.0-only
from __future__ import annotations
import fcntl, os
from pathlib import Path

def main() -> None:
    run = Path("/run/bci"); shm = Path("/dev/shm/bci")
    run.mkdir(mode=0o700, parents=True, exist_ok=True)
    shm.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(run, 0o700); os.chmod(shm, 0o700)
    lock_path = run / ".init.lock"
    with lock_path.open("a+b") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        key = run / "master.key"
        if not key.exists():
            fd = os.open(key, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                os.write(fd, os.urandom(32)); os.fsync(fd)
            finally:
                os.close(fd)
        os.chmod(key, 0o600)
        arm = run / "arm"
        if not arm.exists():
            arm.write_text("LOCKED\n", encoding="utf-8")
        os.chmod(arm, 0o600)

if __name__ == "__main__":
    main()
