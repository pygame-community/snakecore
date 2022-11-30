"""This file is a part of the source code for snakecore.
This project has been licensed under the MIT license.
Copyright (c) 2022-present pygame-community

This file defines regular expressions useful
for parsing information out of Discord text.
"""

URL = r"\w+:\/\/((?:[\w_.-]+@)?[\w_-]+(?:(?:\.[\w_-]+)+))([\w.,@?^=%&:\/~+#-]*[\w@?^=%&\/~+#-])"
"""Matches a URL with any protocol."""
HTTP_URL = r"https?:\/\/((?:[\w_.-]+@)?[\w_-]+(?:(?:\.[\w_-]+)+))([\w.,@?^=%&:\/~+#-]*[\w@?^=%&\/~+#-])"
"""Matches a URL with the HTTP(S) protocol."""


def url_with_protocols(*protocols: str) -> str:
    """Return a regex URL that will match one of the specified protocols.

    Returns
    -------
    str
        The resulting regex pattern string.
    """
    if not protocols:
        raise TypeError("a protocol string must be provided.")
    return rf"({'|'.join(protocols)}){URL[3]}"


CODE_BLOCK = r"```([^`\s]*)\n(((?!```).|\s|(?<=\\)```)+)```"
"""Matches a Discord fenced code block. Triple backticks are supported
in text content if preceded by a backslash.

Groups
------
  1. The language.
  2. The text content.
"""

INLINE_CODE_BLOCK = r"`((?:(?<=\\)`|[^`\n])+)`"
"""Matches a Discord inline code block. Backticks are supported
in text content if preceded by a backslash.

Groups
------
1. The text content.
"""

USER_ROLE_MENTION = r"<@[&!]?(\d+)>"
"""Matches a Discord user or role mention ('<@[!]6969...>'  
or '<@&6969...>').

Groups
------
1. The mentioned target's integer ID.
"""

USER_ROLE_CHANNEL_MENTION = r"<(?:@[&!]?|\#)(\d+)>"
"""Matches a Discord user, role or channel mention ('<@[!]6969...>', 
'<@&6969...>' or '<#6969...>').

Groups
------
1. The mentioned target's integer ID.
"""

USER_MENTION = r"<@!?(\d+)>"
"""Matches a Discord user mention ('<@[!]6969...>').

Groups
------
1. The mentioned target's integer ID.
"""

ROLE_MENTION = r"<@&(\d+)>"
"""Matches a Discord role mention ('<@&6969...>').

Groups
------
1. The mentioned target's integer ID.
"""

CHANNEL_MENTION = r"<#(\d+)>"
"""Matches a Discord channel mention ('<#6969...>').

Groups
------
1. The mentioned target's integer ID.
"""

CUSTOM_EMOJI = r"<(a?):(\S+):(\d+)>"
"""Matches a Discord custom emoji ('<[a]:emoji_name:emoji_id>').

Groups
------
1. The 'a' character indicating that an emoji is animated, if present.
2. The emoji name.
3. The emoji integer ID.
"""

EMOJI_SHORTCODE = r"\s*:(\S+):\s*"
"""Matches a Discord emoji shortcode. (':emoji_name:').

Groups
------
1. The shortcode name.
"""

UNIX_TIMESTAMP = r"<t:(-?\d+)(?::([tTdDfFR]))?>"
"""Matches a Discord UNIX timestamp in seconds ('<t:6969...[:t|T|d|D|f|F|R]>').

Groups
------
1. The UNIX timestamp integer in seconds.
2. The timestamp formatting used on Discord. Can be t, T, d, D, f, F, or R .
"""
SLASH_COMMAND = APP_COMMAND = r"</(.+):(\d+)>"
"""Matches a Discord slash command mention. ('</lol:6969...>').

Groups
------
1. The slash command name.
2. The slash command integer ID.
"""
TIME = r"[Tt]?(?:([0-2]?\d)(?<!2[4-9])(?::([0-5]\d))?(?::([0-5]\d)(?:\.(\d+))?)?\s*([AaPp][Mm])?)(?:,|;)?\s*((\w{0,10})?(?:([+-])([0-2]?\d)(?<!2[4-9])(?::([0-5]\d))?(?::([0-5]\d)(?:\.(\d+))?)?)?)?"
"""Matches a string denoting time, with(out) time zone information.

Examples
--------
- 6 pm
- 8:29PM +03
- 23:59 GMT-5:30
- 9:45:59 AM PST
- 13:30:01 BST
- 0:33:09 CEST

Groups
------
1. The hour(s) (0-23).
2. The minute(s) (0-59). Can be empty.
3. The second(s) (0-59). Can be empty.
4. The microseconds(s). Can be empty.
5. AM or PM (case insensitive). Can be empty.
6. Full time zone information (e.g. "UTC-5:30"). Contains groups 6 and above. Can be empty.
7. The time zone name (e.g. PST). Can be empty.
8. The time zone offset direction, as "+" or "-". Is required for groups 9 and above to be non-empty. Can be empty.
9. The hour(s) (0-23)  of the time-zone offset.
10. The minute(s) (0-59) of the time-zone offset. Can be empty.
11. The second(s) (0-59) of the time-zone offset. Can be empty.
12. The microsecond(s) of the time-zone offset. Can be empty.
"""

TIME_INTERVAL = r"(?:(?:(\d+)\:)?(?:([0-2]?\d)(?<!2[4-9])\:))?(?:([0-5]?\d)\:)(?:([0-5]?\d)(?:.(\d+))?)"
"""Matches a string denoting a time interval using colon-separated integers.

Examples
--------
- 1:30 (1m 30s)
- 245:23:00:59 (245d 23h 59s)

Groups
------
1. The days. Can be empty.
2. The hours (0-24). Can be empty.
3. The minutes (0-59).
4. The seconds (0-59).
5. The microseconds.
"""

TIME_INTERVAL_PHRASE = r"[Pp]?[Tt]?(?=\d)(?:(?:(\d+\.?\d+)\s{0,3}(?:[Ww](?:ks?|eeks?)?\.?))?\s*(?:(\d+\.?\d+)\s{0,3}(?:[Dd](?:ays?)?\.?))?\s*(?:(\d+\.?\d+)\s{0,3}(?:[Hh](?:rs?|ours?)?\.?))?\s*(?:(\d+\.?\d+)\s{0,3}(?:[Mm](?:in(?:s|utes?)?)?\.?))?\s*(?:(\d+\.?\d+)\s{0,3}(?:[Ss](?:ec(?:s|onds?)?)?\.?))?)(?<=[sSrmMnhHdDwW])"
"""Matches a string denoting a time interval using numbers followed by their time
specifiers. Floating point numbers are supported.

Examples
--------
- 1:30 1m 30s
- 245d 23h 59s
- 420w69s
- 3.234 seconds

Groups
------
1. The weeks. Can be empty.
2. The days. Can be empty.
3. The hours. Can be empty.
4. The minutes.
5. The seconds.
"""
