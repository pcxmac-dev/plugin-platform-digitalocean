"""A change refused before anything is sent, and why."""
from __future__ import annotations


class Refusal(ValueError):
    """A change not made, and why: nothing was sent to DigitalOcean. `accept`: the hook's argument that, set, makes the
    change anyway (accept_hard for a hard power-off, accept_risky for a risky firewall rule); the platform's page asks it
    as a second, explicit confirmation, with the words of the form's field of that name."""

    def __init__(self, message: str, accept: str | None = None):
        super().__init__(message)
        self.accept = accept
