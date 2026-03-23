"""Standardized date key constants for voice command parameter examples.

These keys are used in adapter training data and prompt examples for any
command that accepts date/time parameters. The node's date resolver
converts these keys to actual datetime objects at runtime.

Usage:
    from jarvis_command_sdk import DateKeys

    CommandExample(
        voice_command="What's on my calendar today?",
        expected_parameters={"resolved_datetimes": [DateKeys.TODAY]},
    )
"""


class DateKeys:
    """Relative date key constants resolved by the server at runtime."""

    TODAY = "today"
    TOMORROW = "tomorrow"
    DAY_AFTER_TOMORROW = "day_after_tomorrow"
    YESTERDAY = "yesterday"
    THIS_WEEKEND = "this_weekend"
    NEXT_WEEK = "next_week"
    LAST_WEEKEND = "last_weekend"
    NEXT_MONDAY = "next_monday"
    NEXT_TUESDAY = "next_tuesday"
    NEXT_WEDNESDAY = "next_wednesday"
    NEXT_THURSDAY = "next_thursday"
    NEXT_FRIDAY = "next_friday"
    NEXT_SATURDAY = "next_saturday"
    NEXT_SUNDAY = "next_sunday"
    MORNING = "morning"
    TONIGHT = "tonight"
    LAST_NIGHT = "last_night"
    TOMORROW_NIGHT = "tomorrow_night"
    TOMORROW_MORNING = "tomorrow_morning"
    TOMORROW_AFTERNOON = "tomorrow_afternoon"
    TOMORROW_EVENING = "tomorrow_evening"
    YESTERDAY_MORNING = "yesterday_morning"
    YESTERDAY_AFTERNOON = "yesterday_afternoon"
    YESTERDAY_EVENING = "yesterday_evening"


ALL_DATE_KEYS = [
    DateKeys.DAY_AFTER_TOMORROW,
    DateKeys.LAST_NIGHT,
    DateKeys.LAST_WEEKEND,
    DateKeys.MORNING,
    DateKeys.NEXT_FRIDAY,
    DateKeys.NEXT_MONDAY,
    DateKeys.NEXT_SATURDAY,
    DateKeys.NEXT_SUNDAY,
    DateKeys.NEXT_THURSDAY,
    DateKeys.NEXT_TUESDAY,
    DateKeys.NEXT_WEEK,
    DateKeys.NEXT_WEDNESDAY,
    DateKeys.THIS_WEEKEND,
    DateKeys.TODAY,
    DateKeys.TOMORROW,
    DateKeys.TOMORROW_AFTERNOON,
    DateKeys.TOMORROW_EVENING,
    DateKeys.TOMORROW_MORNING,
    DateKeys.TOMORROW_NIGHT,
    DateKeys.TONIGHT,
    DateKeys.YESTERDAY,
    DateKeys.YESTERDAY_AFTERNOON,
    DateKeys.YESTERDAY_EVENING,
    DateKeys.YESTERDAY_MORNING,
]
