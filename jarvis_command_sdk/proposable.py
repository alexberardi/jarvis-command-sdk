"""Proposable actions — the generic, opt-in contract that lets ANY agent
surface ANY command's callback as a tap-to-confirm card.

Today a command's ``@callback`` methods are reachable by the node's callback
transport *by name*, with no check on who posted the card (see the
command-center dispatcher). That is powerful but unsafe: it means any installed
agent could fire any callback with an arbitrary ``data`` dict. This module adds
the missing half — a **declaration** a command makes about which of its
callbacks may be proposed, with typed params and a card presentation. The
declaration IS the capability grant: a callback absent from ``proposable_actions``
is refused by the command-center dispatcher, so an agent cannot invent a target.

Flow:
    command declares ``proposable_actions`` (opt-in)  ─┐
    agent calls ``JarvisInbox.propose_action(...)``    ─┤→ server-plane confirm card
    user taps Confirm → CC's single generic dispatcher validates against this
    declaration (opt-in + typed params + blast tier + idempotency) → runs the
    command's ``@callback`` on the node.

Reuses existing SDK primitives: :class:`JarvisParameter` for typed inputs and
:class:`FieldSpec` for declared outputs (future step-to-step wiring).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .parameter import JarvisParameter
from .field_spec import FieldSpec


class BlastTier(str, Enum):
    """How consequential running a proposable action is.

    Drives *card presentation* only (not who may propose — the confirmation tap
    is the gate for every tier). ``irreversible`` actions (spend money, contact
    a stranger, hard-to-undo) warrant an extra acknowledgement beyond a single
    tap; ``reversible`` (add a calendar event) is a single confirm.
    """

    reversible = "reversible"
    irreversible = "irreversible"


@dataclass
class ProposableAction:
    """One callback a command opts in to being proposed as a confirm card.

    Attributes:
        callback: The ``@callback`` name on THIS command that runs when the user
            confirms. MUST match a decorated method (validated at discovery by
            :meth:`IJarvisCommand.get_proposable_actions`).
        params: Typed inputs the action accepts (reuses :class:`JarvisParameter`
            — type/required/enum). The command-center dispatcher validates the
            proposed ``data`` against these before executing.
        outputs: Declared typed outputs (reuses :class:`FieldSpec`), for future
            step-to-step wiring / multi-step errands. Optional today.
        card_title: Default title for the confirm card ("Add to your calendar?").
        confirm_label / dismiss_label: Button labels ("Add" / "Dismiss").
        editable: Subset of ``params`` names the user may correct on the card
            (e.g. a mis-parsed datetime). Must be a subset of ``params``.
        blast_tier: Presentation tier (see :class:`BlastTier`).
        idempotency_param: Names the param carrying the stable dedup key. The
            **contract**: command-center de-dupes *dispatch* on this key, but the
            command MUST also no-op if a record with this key already exists —
            that is the only guard against a timeout-after-success double-write.
    """

    callback: str
    params: list[JarvisParameter] = field(default_factory=list)
    outputs: list[FieldSpec] = field(default_factory=list)
    card_title: str = ""
    confirm_label: str = "Confirm"
    dismiss_label: str = "Dismiss"
    editable: list[str] = field(default_factory=list)
    blast_tier: BlastTier = BlastTier.reversible
    idempotency_param: str | None = None

    def __post_init__(self) -> None:
        if not self.callback or not str(self.callback).strip():
            raise ValueError("ProposableAction 'callback' must be a non-empty string")
        if not isinstance(self.blast_tier, BlastTier):
            # Coerce a plain string ("reversible") to the enum; raises on unknown.
            self.blast_tier = BlastTier(self.blast_tier)
        param_names = {p.name for p in self.params}
        unknown = [e for e in self.editable if e not in param_names]
        if unknown:
            raise ValueError(
                f"ProposableAction '{self.callback}': editable names not in params: {unknown}"
            )
        if self.idempotency_param is not None and self.idempotency_param not in param_names:
            raise ValueError(
                f"ProposableAction '{self.callback}': idempotency_param "
                f"'{self.idempotency_param}' is not a declared param"
            )

    def to_dict(self) -> dict[str, Any]:
        """Wire form advertised to command-center (which never imports the SDK).

        The command-center capability registry stores these dicts; the dispatcher
        validates a proposed action against them.
        """
        return {
            "callback": self.callback,
            "params": [p.to_dict() for p in self.params],
            "outputs": [o.to_dict() for o in self.outputs],
            "card_title": self.card_title,
            "confirm_label": self.confirm_label,
            "dismiss_label": self.dismiss_label,
            "editable": list(self.editable),
            "blast_tier": self.blast_tier.value,
            "idempotency_param": self.idempotency_param,
        }
