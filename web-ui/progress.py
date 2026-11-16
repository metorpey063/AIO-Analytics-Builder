"""
progress.py — replayable progress channel for background jobs.

A plain queue.Queue hands each message to exactly one reader, so a page reload or a second
tab loses messages, and a job nobody is watching fills its queue forever. A ProgressChannel
keeps a bounded, append-only event list instead: every SSE reader walks it with its own
cursor, a reload replays the job from the start, and EventSource's automatic reconnect
resumes from Last-Event-ID.

The channel has the one Queue method the builders use (put), so it drops in wherever a
queue was passed.
"""

import threading

TERMINAL_STAGES = ("done", "error")
MAX_EVENTS = 5000          # per job; older events are dropped (cursors stay valid)
MAX_FINISHED_CHANNELS = 20  # finished jobs kept for replay


class ProgressChannel:
    def __init__(self):
        self._events = []
        self._offset = 0          # absolute index of self._events[0]
        self._cond = threading.Condition()
        self.finished = False
        self.thread = None        # the job's thread, set by the caller once started

    def put(self, msg: dict):
        with self._cond:
            self._events.append(msg)
            if len(self._events) > MAX_EVENTS:
                drop = len(self._events) - MAX_EVENTS
                del self._events[:drop]
                self._offset += drop
            if msg.get("stage") in TERMINAL_STAGES:
                self.finished = True
            self._cond.notify_all()

    def running(self) -> bool:
        """True while the job can still produce events."""
        if self.finished:
            return False
        return self.thread is None or self.thread.is_alive()

    def read_from(self, cursor: int, timeout: float = 30):
        """Events at absolute index >= cursor, waiting up to `timeout` for one to arrive.
        Returns (events, next_cursor); events are (index, msg) pairs."""
        with self._cond:
            if cursor >= self._offset + len(self._events) and not self.finished:
                self._cond.wait(timeout)
            start = max(cursor, self._offset)
            out = [(self._offset + i, m)
                   for i, m in enumerate(self._events[start - self._offset:], start - self._offset)]
            return out, self._offset + len(self._events)


def prune(channels: dict):
    """Drop the oldest finished channels beyond MAX_FINISHED_CHANNELS. Running ones stay."""
    done = [k for k, ch in channels.items() if not ch.running()]
    for k in done[:max(0, len(done) - MAX_FINISHED_CHANNELS)]:
        channels.pop(k, None)
