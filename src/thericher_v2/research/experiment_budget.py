"""Dual clocks for the canonical analytical runner; no I/O or trading authority."""

import math
import time
from contextlib import contextmanager
from typing import Protocol


class BudgetProtocol(Protocol):
    def check(self, *, publication: bool = False) -> None: ...


class BudgetExceeded(RuntimeError):
    """This experiment exhausted a predeclared clock, not another lane's authority."""


def _number(value):
    try:
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ValueError("budget_number_invalid")
        return float(value)
    except OverflowError:
        raise ValueError("budget_number_invalid") from None


class DualClockBudget:
    """One frozen appointment and carried debit; worker scopes include cleanup."""

    def __init__(self, *, appointment_epoch, active_cap, end_cap, active_charged=0.0,
                 elapsed_charged=0.0, clock_failed=False,
                 reserve=0.0, wall=time.time, mono=time.monotonic):
        appointment, active, end, charged, elapsed, reserve = map(
            _number, (appointment_epoch, active_cap, end_cap, active_charged,
                      elapsed_charged, reserve)
        )
        if type(clock_failed) is not bool:
            raise ValueError("budget_clock_state_invalid")
        if not callable(wall) or not callable(mono) or not 0 <= reserve < min(active, end):
            raise ValueError("budget_caps_invalid")
        initial_wall, initial_mono = _number(wall()), _number(mono())
        if appointment > initial_wall:
            raise ValueError("future_appointment")
        self._limits = appointment, active, end, reserve
        self._wall, self._mono = wall, mono
        self._start = self._last = initial_mono
        self._age = self._elapsed = max(elapsed, initial_wall - appointment)
        self._charged, self._entered, self._broken = charged, None, clock_failed

    def _sample_mono(self):
        now = _number(self._mono())
        if now < self._last:
            raise ValueError("budget_clock_invalid")
        self._last = now
        return now

    def _usage(self):
        if self._broken:
            raise ValueError("budget_clock_invalid")
        try:
            now = self._sample_mono()
            wall = _number(self._wall())
            self._elapsed = max(self._elapsed, wall - self._limits[0],
                                self._age + (now - self._start))
        except Exception:
            self._broken = True
            raise ValueError("budget_clock_invalid") from None
        active = self._charged + (now - self._entered if self._entered is not None else 0)
        return active, self._elapsed

    @property
    def charged(self):
        return self._charged

    @property
    def active(self):
        return self._usage()[0]

    @property
    def elapsed(self):
        return self._usage()[1]

    def check(self, *, publication: bool = False) -> None:
        if type(publication) is not bool:
            raise TypeError("publication_boolean")
        active, elapsed = self._usage()
        reserve = 0 if publication else self._limits[3]
        if active >= self._limits[1] - reserve:
            raise BudgetExceeded("active_owned_worker_cap")
        if elapsed >= self._limits[2] - reserve:
            raise BudgetExceeded("end_to_end_cap")

    @contextmanager
    def owned_worker(self, *, publication: bool = False):
        if self._entered is not None:
            raise ValueError("nested_owner_scope")
        self.check(publication=publication)
        self._entered, failed = self._last, False
        try:
            yield self
        except BaseException:
            failed = True
            raise
        finally:
            try:
                # A failed wall clock still permits monotonic cleanup accounting,
                # never another worker appointment or a restored clock allowance.
                try:
                    self._sample_mono()
                except Exception:
                    self._broken = True
                self._elapsed = max(self._elapsed, self._age + self._last - self._start)
                self._charged += self._last - self._entered
                self._entered = None
                self.check(publication=True)
            except Exception:
                if not failed:
                    raise

    def snapshot(self):
        """Caller persists debit, elapsed high-water and fault flag together."""
        try:
            active, elapsed = self._usage()
        except ValueError:
            active = self._charged + (self._last - self._entered
                                      if self._entered is not None else 0)
            elapsed = self._elapsed
        return dict(appointment_epoch=self._limits[0], active_owned_seconds=active,
                    end_to_end_seconds=elapsed, active_cap=self._limits[1], end_cap=self._limits[2],
                    clock_failed=self._broken)
