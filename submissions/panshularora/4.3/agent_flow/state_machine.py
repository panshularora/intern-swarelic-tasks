"""Agent availability state machine."""
from enum import Enum, auto
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Optional


class AgentState(Enum):
    OFFLINE     = auto()
    ONLINE      = auto()
    AVAILABLE   = auto()
    RINGING     = auto()
    ON_CALL     = auto()
    WRAPPING_UP = auto()
    BREAK       = auto()


class AgentEvent(Enum):
    LOGIN         = auto()
    READY         = auto()
    CALL_RECEIVED = auto()
    CALL_ACCEPTED = auto()
    CALL_REJECTED = auto()
    CALL_ENDED    = auto()
    WRAP_UP_DONE  = auto()
    TAKE_BREAK    = auto()
    END_BREAK     = auto()
    LOGOUT        = auto()


class InvalidTransitionError(Exception):
    """Raised when an event is not valid in the current state."""
    def __init__(self, state: AgentState, event: AgentEvent):
        self.state = state
        self.event = event
        super().__init__(
            f"Cannot trigger '{event.name}' from state '{state.name}'"
        )


@dataclass
class StateTransition:
    from_state: AgentState
    event: AgentEvent
    to_state: AgentState
    guard: Optional[Callable] = None
    on_enter: Optional[Callable] = None


class AgentStateMachine:
    """
    Valid transitions:
    OFFLINE     + LOGIN         → ONLINE
    ONLINE      + READY         → AVAILABLE
    ONLINE      + LOGOUT        → OFFLINE
    AVAILABLE   + CALL_RECEIVED → RINGING
    AVAILABLE   + TAKE_BREAK    → BREAK
    AVAILABLE   + LOGOUT        → OFFLINE
    RINGING     + CALL_ACCEPTED → ON_CALL
    RINGING     + CALL_REJECTED → AVAILABLE
    ON_CALL     + CALL_ENDED    → WRAPPING_UP
    WRAPPING_UP + WRAP_UP_DONE  → AVAILABLE
    BREAK       + END_BREAK     → AVAILABLE
    BREAK       + LOGOUT        → OFFLINE
    """

    TRANSITIONS: list[StateTransition] = [
        StateTransition(AgentState.OFFLINE, AgentEvent.LOGIN, AgentState.ONLINE),
        StateTransition(AgentState.ONLINE, AgentEvent.READY, AgentState.AVAILABLE),
        StateTransition(AgentState.ONLINE, AgentEvent.LOGOUT, AgentState.OFFLINE),
        StateTransition(AgentState.AVAILABLE, AgentEvent.CALL_RECEIVED, AgentState.RINGING),
        StateTransition(AgentState.AVAILABLE, AgentEvent.TAKE_BREAK, AgentState.BREAK),
        StateTransition(AgentState.AVAILABLE, AgentEvent.LOGOUT, AgentState.OFFLINE),
        StateTransition(AgentState.RINGING, AgentEvent.CALL_ACCEPTED, AgentState.ON_CALL),
        StateTransition(AgentState.RINGING, AgentEvent.CALL_REJECTED, AgentState.AVAILABLE),
        StateTransition(AgentState.ON_CALL, AgentEvent.CALL_ENDED, AgentState.WRAPPING_UP),
        StateTransition(AgentState.WRAPPING_UP, AgentEvent.WRAP_UP_DONE, AgentState.AVAILABLE),
        StateTransition(AgentState.BREAK, AgentEvent.END_BREAK, AgentState.AVAILABLE),
        StateTransition(AgentState.BREAK, AgentEvent.LOGOUT, AgentState.OFFLINE),
    ]

    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.state = AgentState.OFFLINE
        self.history: list[dict] = []
        self._state_entered_at = datetime.now()
        self._current_call_id: str | None = None

    def _match(self, event: AgentEvent) -> StateTransition | None:
        for transition in self.TRANSITIONS:
            if transition.from_state == self.state and transition.event == event:
                return transition
        return None

    def trigger(self, event: AgentEvent, **metadata) -> AgentState:
        transition = self._match(event)
        if transition is None:
            raise InvalidTransitionError(self.state, event)
        if transition.guard is not None and not transition.guard(self, **metadata):
            raise InvalidTransitionError(self.state, event)

        from_state = self.state
        to_state = transition.to_state
        self._record_transition(event, from_state, to_state, **metadata)
        self.state = to_state
        self._state_entered_at = datetime.now()
        if event == AgentEvent.CALL_RECEIVED:
            self._current_call_id = metadata.get('call_id')
        if event in (AgentEvent.CALL_ENDED, AgentEvent.CALL_REJECTED, AgentEvent.LOGOUT):
            self._current_call_id = None
        if transition.on_enter is not None:
            transition.on_enter(self, **metadata)
        return self.state

    def can_trigger(self, event: AgentEvent) -> bool:
        return self._match(event) is not None

    def _record_transition(self, event: AgentEvent, from_state: AgentState,
                            to_state: AgentState, **metadata):
        self.history.append({
            'timestamp': datetime.now().isoformat(),
            'agent_id': self.agent_id,
            'from_state': from_state.name,
            'event': event.name,
            'to_state': to_state.name,
            'metadata': metadata,
        })

    def get_history(self) -> list[dict]:
        return self.history
