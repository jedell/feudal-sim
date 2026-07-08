"""
EventLog — circular buffer of simulation events in POSIX shared memory.

Layout:
  [0:4]   int32  write_head (next slot to write, 0-19)
  [4:...]  20 × 80-byte null-terminated strings

Total: 4 + 20 × 80 = 1604 bytes.
"""

import struct
import multiprocessing.shared_memory as shm

MAX_EVENTS = 20
EVENT_SIZE = 80
HEADER_SIZE = 4
TOTAL_SIZE = HEADER_SIZE + MAX_EVENTS * EVENT_SIZE


class EventLog:
    SHM_NAME = "psm_events"

    def __init__(self):
        try:
            self._shm = shm.SharedMemory(name=self.SHM_NAME, create=True, size=TOTAL_SIZE)
        except FileExistsError:
            # Stale segment from a previous run — unlink and recreate
            old = shm.SharedMemory(name=self.SHM_NAME, create=False, size=TOTAL_SIZE)
            old.unlink()
            old.close()
            self._shm = shm.SharedMemory(name=self.SHM_NAME, create=True, size=TOTAL_SIZE)
        # Zero-initialise
        self._shm.buf[:TOTAL_SIZE] = b'\x00' * TOTAL_SIZE

    def log_event(self, text: str) -> None:
        head = struct.unpack_from('<i', self._shm.buf, 0)[0]
        encoded = text[:EVENT_SIZE - 1].encode('utf-8', errors='replace').ljust(EVENT_SIZE, b'\x00')
        offset = HEADER_SIZE + head * EVENT_SIZE
        self._shm.buf[offset:offset + EVENT_SIZE] = encoded
        struct.pack_into('<i', self._shm.buf, 0, (head + 1) % MAX_EVENTS)

    def close(self):
        try:
            self._shm.close()
            self._shm.unlink()
        except Exception:
            pass
