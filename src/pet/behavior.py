"""Pet behavior state machine — maps agent states to pet animations."""

from __future__ import annotations

import time
from enum import Enum, auto

import structlog

log = structlog.get_logger("assistant.pet.behavior")


class AgentState(Enum):
    IDLE = auto()           # Waiting → pet walks around freely
    PROCESSING = auto()     # Thinking → pet types on keyboard, stays still
    EXECUTING = auto()      # Running command → pet runs across monitors
    ERROR = auto()          # Error → pet is sad, stays still
    COMPLETE = auto()       # Done → brief happy idle, then walk
    INACTIVE = auto()       # Long idle → pet sleeps, stays still

    @classmethod
    def from_string(cls, s: str) -> "AgentState":
        return cls[s.upper()] if s.upper() in cls.__members__ else cls.IDLE


_STATE_TO_ANIMATION: dict[AgentState, str] = {
    AgentState.IDLE: "idle",
    AgentState.PROCESSING: "type",
    AgentState.EXECUTING: "run",
    AgentState.ERROR: "sad",
    AgentState.COMPLETE: "idle",
    AgentState.INACTIVE: "sleep",
}

# States where pet STAYS STILL
STILL_STATES = {AgentState.PROCESSING, AgentState.ERROR, AgentState.INACTIVE}

# States where pet MOVES
MOVING_STATES = {AgentState.IDLE, AgentState.COMPLETE, AgentState.EXECUTING}

_TRANSIENT_DURATIONS: dict[AgentState, float] = {
    AgentState.COMPLETE: 5.0,
    AgentState.ERROR: 10.0,
}

INACTIVITY_TIMEOUT = 5 * 60


class BehaviorController:

    def __init__(self) -> None:
        self._state = AgentState.IDLE
        self._state_time = time.time()
        self._last_activity = time.time()
        self._state_changed = False

    @property
    def state(self) -> AgentState:
        return self._state

    @property
    def animation(self) -> str:
        return _STATE_TO_ANIMATION.get(self._state, "idle")

    @property
    def should_stay_still(self) -> bool:
        return self._state in STILL_STATES

    @property
    def should_move(self) -> bool:
        return self._state in MOVING_STATES

    @property
    def state_just_changed(self) -> bool:
        """True if state changed since last check. Resets after reading."""
        if self._state_changed:
            self._state_changed = False
            return True
        return False

    def set_state(self, state: AgentState) -> str:
        now = time.time()
        if state != AgentState.INACTIVE:
            self._last_activity = now
        if state != self._state:
            old = self._state
            self._state = state
            self._state_time = now
            self._state_changed = True
            log.debug("behavior.state_changed", old=old.name, new=state.name)
        return self.animation

    def tick(self) -> str | None:
        now = time.time()
        elapsed = now - self._state_time
        if self._state in _TRANSIENT_DURATIONS:
            if elapsed >= _TRANSIENT_DURATIONS[self._state]:
                return self.set_state(AgentState.IDLE)
        if self._state == AgentState.IDLE:
            if now - self._last_activity >= INACTIVITY_TIMEOUT:
                return self.set_state(AgentState.INACTIVE)
        return None

    def on_message_received(self) -> str:
        return self.set_state(AgentState.PROCESSING)

    def on_execution_start(self) -> str:
        return self.set_state(AgentState.EXECUTING)

    def on_response_sent(self, success: bool = True) -> str:
        return self.set_state(AgentState.COMPLETE if success else AgentState.ERROR)

    def on_idle(self) -> str:
        return self.set_state(AgentState.IDLE)

    def wake_up(self) -> str:
        if self._state == AgentState.INACTIVE:
            return self.set_state(AgentState.IDLE)
        return self.animation
