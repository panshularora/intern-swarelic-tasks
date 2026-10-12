"""Session wrapper: state machine + timing metrics."""
from datetime import datetime
from .state_machine import AgentStateMachine, AgentState, AgentEvent, InvalidTransitionError


class AgentSession:
    """Wraps AgentStateMachine and tracks timing/performance metrics."""

    def __init__(self, agent_id: str):
        self.machine = AgentStateMachine(agent_id)
        self.session_start = datetime.now()
        self._calls_handled = 0
        self._total_call_time_secs = 0.0
        self._total_wrap_time_secs = 0.0
        self._available_time_secs = 0.0
        self._online_time_secs = 0.0
        self._last_state_change = self.session_start

    def _accrue(self, until: datetime) -> None:
        elapsed = (until - self._last_state_change).total_seconds()
        if elapsed < 0:
            elapsed = 0.0
        state = self.machine.state
        if state != AgentState.OFFLINE:
            self._online_time_secs += elapsed
        if state == AgentState.AVAILABLE:
            self._available_time_secs += elapsed
        elif state == AgentState.ON_CALL:
            self._total_call_time_secs += elapsed
        elif state == AgentState.WRAPPING_UP:
            self._total_wrap_time_secs += elapsed

    def process_event(self, event: AgentEvent, **kwargs) -> dict:
        """
        Process an event through the state machine.
        Returns dict: success, new_state, error.
        """
        now = datetime.now()
        try:
            self._accrue(now)
            new_state = self.machine.trigger(event, **kwargs)
        except InvalidTransitionError as exc:
            return {
                'success': False,
                'new_state': self.machine.state.name,
                'error': str(exc),
            }

        self._last_state_change = now
        if event == AgentEvent.CALL_ENDED:
            self._calls_handled += 1
        return {
            'success': True,
            'new_state': new_state.name,
            'error': None,
        }

    def get_metrics(self) -> dict:
        now = datetime.now()
        self._accrue(now)
        self._last_state_change = now

        session_duration = (now - self.session_start).total_seconds()
        if self._calls_handled:
            avg_call = self._total_call_time_secs / self._calls_handled
        else:
            avg_call = 0.0
        if self._online_time_secs > 0:
            availability = (self._available_time_secs / self._online_time_secs) * 100
        else:
            availability = 0.0

        return {
            'agent_id': self.machine.agent_id,
            'current_state': self.machine.state.name,
            'session_duration_secs': session_duration,
            'calls_handled': self._calls_handled,
            'avg_call_duration_secs': avg_call,
            'total_wrap_time_secs': self._total_wrap_time_secs,
            'availability_pct': availability,
        }
