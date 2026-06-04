"""Summary shape used by the mobile command-data browser list row.

A command's `display_summary(record)` returns one of these so the mobile
"records list" can render an icon + title + optional subtitle without the
mobile app needing to understand the command's storage shape.

Icons are free-form MaterialCommunityIcons name strings (the same vocabulary
react-native-paper's `Icon` component accepts and the same one IJarvisButton
already uses for `button_icon`). Mobile falls back to a generic icon for
unknown names; there's no closed registry in the SDK.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


DataBrowserMode = Literal["enabled", "disabled", "readonly"]
"""Whether and how a command's stored data appears in the mobile data browser.

- "enabled" (default): list, view detail, edit, delete.
- "disabled": not shown at all. Node filters before serialising.
- "readonly": list + view detail, no edit, no delete. Reserved for future
  mobile support; older mobile builds that don't recognise the value hide
  the section so commands shipping `readonly` aren't accidentally exposed
  as fully editable.

Wire format is a plain string so new modes can ship without breaking older
command-center or mobile builds. Node-side filtering only drops `disabled`;
unknown values pass through and mobile chooses how to render.
"""


@dataclass
class RecordSummary:
    """Title/subtitle/icon shown for one record in the browser list.

    Attributes:
        title: Primary display text (e.g. the reminder's `text`).
        subtitle: Secondary line (e.g. due-at formatted, status).
        icon: MaterialCommunityIcons name (e.g. "bell", "clock-outline").
            Free-form string; unknown names fall back to a generic icon on
            mobile.
    """

    title: str
    subtitle: str | None = None
    icon: str = "information-outline"

    def to_dict(self) -> dict[str, str | None]:
        return {
            "title": self.title,
            "subtitle": self.subtitle,
            "icon": self.icon,
        }
