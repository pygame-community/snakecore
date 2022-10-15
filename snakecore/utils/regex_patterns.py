"""
This file is a part of the source code for snakecore.
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

    Returns:
        str: The resulting regex pattern string.
    """
    if not protocols:
        raise TypeError("a protocol string must be provided.")
    return rf"({'|'.join(protocols)}){URL[3]}"


CODE_BLOCK = r"```([^`\s]*)\n(((?!```).|\s|(?<=\\)```)+)```"
"Matches a fenced code block."
INLINE_CODE_BLOCK = r"`((?:(?<=\\)`|[^`\n])+)`"
"Matches an inline code block (`...`)."
USER_ROLE_MENTION = r"<@[&!]?(\d+)>"
"""Matches a Discord user or role mention ('<@[!]6969...>'  
or '<@&6969...>').
"""
USER_ROLE_CHANNEL_MENTION = r"<(?:@[&!]?|\#)(\d+)>"
"""Matches a Discord user, role or channel mention ('<@[!]6969...>', 
'<@&6969...>' or '<#6969...>').
"""
USER_MENTION = r"<@!?(\d+)>"
"Matches a Discord user mention ('<@[!]6969...>')."
ROLE_MENTION = r"<@&(\d+)>"
"Matches a Discord role mention ('<@&6969...>')."
CHANNEL_MENTION = r"<#(\d+)>"
"Matches a Discord channel mention ('<#6969...>')."
CUSTOM_EMOJI = r"<(a?):(\S+):(\d+)>"
"Matches a Discord custom emoji ('<[a]:emoji_name:emoji_id>')."
EMOJI_SHORTCODE = r"\s*:(\S+):\s*"
"Matches a Discord emoji shortcode. (':emoji_name:')."
UNIX_TIMESTAMP = r"<t:(-?\d+)(?::([tTdDfFR]))?>"
"Matches a Discord UNIX timestamp. ('<t:6969...[:t|T|d|D|f|F|R]>')."
SLASH_COMMAND = APP_COMMAND = r"</.+:(\d+)>"
"Matches a Discord UNIX timestamp. ('<t:6969...[:t|T|d|D|f|F|R]>')."
