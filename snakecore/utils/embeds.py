"""This file is a part of the source code for snakecore.
This project has been licensed under the MIT license.
Copyright (c) 2022-present pygame-community

This file defines some utility functions for working with discord.py's Embed objects.
"""

import datetime
import io
import json
import re
from ast import literal_eval
from typing import (
    Any,
    Literal,
    Mapping,
    Optional,
    Sequence,
    TypedDict,
    Union,
    overload,
)

import black
import discord

import discord.types.embed

from .utils import recursive_mapping_update
from . import regex_patterns


EMBED_TOP_LEVEL_ATTRIBUTES_MASK_DICT = {
    "provider": None,
    "type": None,
    "title": None,
    "description": None,
    "url": None,
    "color": None,
    "timestamp": None,
    "footer": None,
    "thumbnail": None,
    "image": None,
    "author": None,
    "fields": None,
}

EMBED_TOP_LEVEL_ATTRIBUTES_SET = {
    "provider",
    "type",
    "title",
    "description",
    "url",
    "color",
    "timestamp",
    "footer",
    "thumbnail",
    "image",
    "author",
    "fields",
}

EMBED_SYSTEM_ATTRIBUTES_MASK_DICT = {
    "provider": {
        "name": None,
        "url": None,
    },
    "type": None,
    "footer": {
        "proxy_icon_url": None,
    },
    "thumbnail": {
        "proxy_url": None,
        "width": None,
        "height": None,
    },
    "image": {
        "proxy_url": None,
        "width": None,
        "height": None,
    },
    "author": {
        "proxy_icon_url": None,
    },
}

EMBED_SYSTEM_ATTRIBUTES = {
    "provider",
    "proxy_url",
    "proxy_icon_url",
    "width",
    "height",
    "type",
}

EMBED_NON_SYSTEM_ATTRIBUTES = {
    "name",
    "value",
    "inline",
    "url",
    "image",
    "thumbnail",
    "title",
    "description",
    "color",
    "timestamp",
    "footer",
    "text",
    "icon_url",
    "author",
    "fields",
}

EMBED_ATTRIBUTES_SET = {
    "provider",
    "name",
    "value",
    "inline",
    "url",
    "image",
    "thumbnail",
    "proxy_url",
    "type",
    "title",
    "description",
    "color",
    "timestamp",
    "footer",
    "text",
    "icon_url",
    "proxy_icon_url",
    "author",
    "fields",
}

EMBED_ATTRIBUTES_WITH_SUB_ATTRIBUTES_SET = {
    "author",
    "thumbnail",
    "image",
    "fields",
    "footer",
    "provider",
}  # 'fields' is a special case

EMBED_TOTAL_CHAR_LIMIT = 6000

EMBED_FIELDS_LIMIT = 25

EMBED_CHAR_LIMITS = {
    "author.name": 256,
    "title": 256,
    "description": 4096,
    "fields": 25,
    "field.name": 256,
    "field.value": 1024,
    "footer.text": 2048,
}

CONDENSED_EMBED_DATA_LIST_SYNTAX = """
# Condensed embed data list syntax. String elements that are empty "" will be ignored.
# The list must contain at least one argument.
[
    'author.name' or ('author.name', 'author.url') or ('author.name', 'author.url', 'author.icon_url'),   # embed author

    'title' or ('title', 'url') or ('title', 'url', 'thumbnail.url'),  #embed title, url, thumbnail

    '''desc.''' or ('''desc.''', 'image.url'),  # embed description, image

    0xabcdef, # or -1 for default embed color

    [   # embed fields
    '''
    <field.name|
    ...field.value....
    |field.inline>
    ''',
    ],

    'footer.text' or ('footer.text', 'footer.icon_url'),   # embed footer

    datetime(year, month, day[, hour[, minute[, second[, microsecond]]]]) or '2021-04-17T17:36:00.553' # embed timestamp
]
"""


class FlattenedEmbedDict(TypedDict):
    author_name: Optional[str]
    author_url: Optional[str]
    author_icon_url: Optional[str]
    title: Optional[str]
    url: Optional[str]
    thumbnail_url: Optional[str]
    description: Optional[str]
    image_url: Optional[str]
    color: int
    fields: Optional[Sequence[dict[str, Union[str, bool]]]]
    footer_text: Optional[str]
    footer_icon_url: Optional[str]
    timestamp: Optional[Union[str, datetime.datetime]]


EMBED_MASK_DICT_HINT = dict[
    str,
    Union[
        str,
        int,
        dict[str, Union[str, bool]],
        list[dict[str, Union[str, bool]]],
        datetime.datetime,
    ],
]

EmbedDict = discord.types.embed.Embed


def create_embed_mask_dict(
    attributes: str = "",
    allow_system_attributes: bool = False,
    fields_as_field_dict: bool = False,
) -> EMBED_MASK_DICT_HINT:
    """Create an embed mask dictionary based on the attributes specified in the given
    string. This is mostly used for internal purposes relating to comparing and
    modifying embed dictionaries. All embed attributes are set to `None` by default,
    which will be ignored by `discord.Embed`.

    Parameters
    ----------
    attributes : str, optional
        The attribute string. Defaults to "", which will
        returned all valid attributes of an embed.
    allow_system_attributes : bool, optional
        Whether to include embed attributes that can not be manually set by bot users.
        Defaults to False.
    fields_as_field_dict : bool, optional
        Whether the embed `fields` attribute
        returned in the output dictionary of this function should be a dictionary
        that maps stringized indices to embed field dictionaries. Defaults to False.

    Raises
    ------
    ValueError
        Invalid embed attribute string.

    Returns
    -------
        dict: The generated embed with the specified attributes set to None.
    """

    embed_top_level_attrib_dict = EMBED_TOP_LEVEL_ATTRIBUTES_MASK_DICT
    embed_top_level_attrib_dict = {
        k: v.copy() if isinstance(v, dict) else v
        for k, v in embed_top_level_attrib_dict.items()
    }

    system_attribs_dict = EMBED_SYSTEM_ATTRIBUTES_MASK_DICT
    system_attribs_dict = {
        k: v.copy() if isinstance(v, dict) else v
        for k, v in system_attribs_dict.items()
    }

    all_system_attribs_set = EMBED_SYSTEM_ATTRIBUTES

    embed_mask_dict = {}

    attribs = attributes

    attribs_tuple = tuple(
        attr_str.split(sep=".") if "." in attr_str else attr_str
        for attr_str in attribs.split()
    )

    all_attribs_set = EMBED_ATTRIBUTES_SET | set(str(i) for i in range(25))
    attribs_with_sub_attribs = EMBED_ATTRIBUTES_WITH_SUB_ATTRIBUTES_SET

    for attr in attribs_tuple:
        if isinstance(attr, list):
            if len(attr) > 3:
                raise ValueError(
                    "Invalid embed attribute filter string! "
                    "Sub-attributes do not propagate beyond 3 levels."
                )
            bottom_dict = {}
            for i in range(len(attr)):
                if attr[i] not in all_attribs_set:
                    if i == 1:
                        if attr[i - 1] == "fields" and not re.match(
                            r"(-?\d+)-(-?\d+)(?:\|([-+]?\d+))?", attr[i]
                        ):
                            raise ValueError(
                                f"`{attr[i]}` is not a valid embed (sub-)attribute "
                                "name!"
                            )
                    else:
                        raise ValueError(
                            f"`{attr[i]}` is not a valid embed (sub-)attribute name!"
                        )

                elif attr[i] in all_system_attribs_set and not allow_system_attributes:
                    raise ValueError(
                        f"The given attribute `{attr[i]}` cannot be retrieved when "
                        "`system_attributes=` is set to `False`."
                    )
                if not i:
                    if attribs_tuple.count(attr[i]):
                        raise ValueError(
                            "Invalid embed attribute filter string! "
                            f"Top level embed attribute `{attr[i]}` conflicts with "
                            "its preceding instances."
                        )
                    elif attr[i] not in attribs_with_sub_attribs:
                        raise ValueError(
                            "Invalid embed attribute filter string! "
                            f"The embed attribute `{attr[i]}` does not have any "
                            "sub-attributes!"
                        )

                    if attr[i] not in embed_mask_dict:
                        embed_mask_dict[attr[i]] = bottom_dict
                    else:
                        bottom_dict = embed_mask_dict[attr[i]]

                elif i == 1 and attr[i - 1] == "fields" and not attr[i].isnumeric():
                    if m := re.match(r"(-?\d+)-(-?\d+)(?:\|([-+]?\d+))?", attr[i]):
                        raw_start = start = int(m.group(1))
                        raw_stop = stop = int(m.group(2))
                        raw_step = step = int(m.group(3) or "1")

                        if raw_start <= raw_stop:
                            stop += 1

                        elif raw_start >= raw_stop:
                            stop -= 1
                            if not m.group(3) and raw_step > 0:
                                step *= -1

                        if not (field_range := range(start, stop, step)):
                            raise ValueError(
                                "Invalid embed attribute filter string! "
                                "Embed field integer intervals should not be empty"
                                "and should be structured like this: "
                                "`fields.start-stop[|[+|-]step].attribute`"
                            )

                        sub_attrs = []
                        if attr[i] == attr[-1]:
                            sub_attrs.extend(("name", "value", "inline"))

                        elif attr[-1] in ("name", "value", "inline"):
                            sub_attrs.append(attr[-1])

                        else:
                            raise ValueError(
                                f"`{attr[-1]}` is not a valid embed (sub-)attribute name!",
                            )

                        for j in field_range:
                            str_idx = str(j)
                            if str_idx not in embed_mask_dict["fields"]:
                                embed_mask_dict["fields"][str_idx] = {
                                    sub_attr: None for sub_attr in sub_attrs
                                }
                            else:
                                for sub_attr in sub_attrs:
                                    embed_mask_dict["fields"][str_idx][sub_attr] = None

                        break

                    elif attr[i] in ("name", "value", "inline"):
                        for sub_attr in ("name", "value", "inline"):
                            if attr[i] == sub_attr:
                                for j in range(25):
                                    str_idx = str(j)
                                    if str_idx not in embed_mask_dict["fields"]:
                                        embed_mask_dict["fields"][str_idx] = {
                                            sub_attr: None
                                        }
                                    else:
                                        embed_mask_dict["fields"][str_idx][
                                            sub_attr
                                        ] = None
                                break
                        else:
                            raise ValueError(
                                "Invalid embed attribute filter string! "
                                f"The given attribute `{attr[i]}` is not an "
                                "attribute of an embed field!"
                            )
                        break
                    else:
                        raise ValueError(
                            "Invalid embed attribute filter string! "
                            "Embed field attibutes must be either structutred like"
                            "`fields.0`, `fields.0.attribute`, `fields.attribute` or "
                            "`fields.start-stop[|[+|-]step].attribute`. Note that embed "
                            "field integer intervals cannot contain whitespace."
                        )

                elif i == len(attr) - 1:
                    if attr[i] not in bottom_dict:
                        bottom_dict[attr[i]] = None
                else:
                    if attr[i] not in embed_mask_dict[attr[i - 1]]:
                        bottom_dict = {}
                        embed_mask_dict[attr[i - 1]][attr[i]] = bottom_dict
                    else:
                        bottom_dict = embed_mask_dict[attr[i - 1]][attr[i]]

        elif attr in embed_top_level_attrib_dict:
            if attribs_tuple.count(attr) > 1:
                raise ValueError(
                    "Invalid embed attribute filter string! "
                    "Do not specify top level embed attributes "
                    f"twice when not using the `.` operator: `{attr}`",
                )
            elif attr in all_system_attribs_set and not allow_system_attributes:
                raise ValueError(
                    f"The given attribute `{attr}` cannot be retrieved when "
                    "`system_attributes=` is set to `False`.",
                )

            if attr not in embed_mask_dict:
                embed_mask_dict[attr] = None
            else:
                raise ValueError(
                    "Invalid embed attribute filter string! "
                    "Do not specify upper level embed attributes twice!",
                )

        else:
            raise ValueError(
                f"Invalid top level embed attribute name `{attr}`!",
            )

    if not fields_as_field_dict and "fields" in embed_mask_dict:
        embed_mask_dict["fields"] = [
            embed_mask_dict["fields"][i]
            for i in sorted(embed_mask_dict["fields"].keys())
        ]

    return embed_mask_dict


def split_embed_dict(
    embed_dict: dict[str, Any], divide_code_blocks: bool = True
) -> list[dict[str, Any]]:
    """Split an embed dictionary into multiple valid embed dictionaries based on embed text
    attribute character limits and the total character limit of a single embed in a single
    message. This function will not correct invalid embed attributes or add any missing
    required ones.

    Parameters
    ----------
    embed_dict : dict[str, Any]
        The target embed dictionary.
    divide_code_blocks : bool, optional
        Whether to divide code blocks into two
        valid ones, if they contain a division point of an embed text attribute.
        Defaults to True.

    Returns
    -------
    list[dict[str, Any]]
        A list of newly generated embed dictionaries.
    """

    embed_dict = copy_embed_dict(embed_dict)
    embed_dicts = [embed_dict]
    updated = True

    while updated:
        updated = False
        for i in range(len(embed_dicts)):
            embed_dict = embed_dicts[i]
            if "author" in embed_dict and "name" in embed_dict["author"]:
                author_name = embed_dict["author"]["name"]
                if len(author_name) > EMBED_CHAR_LIMITS["author.name"]:
                    if "title" not in embed_dict:
                        embed_dict["title"] = ""

                    normal_split = True

                    if (
                        (
                            url_matches := tuple(
                                re.finditer(regex_patterns.URL, author_name)
                            )
                        )
                        and (url_match := url_matches[-1]).start()
                        < EMBED_CHAR_LIMITS["author.name"] - 1
                        and url_match.end() > EMBED_CHAR_LIMITS["author.name"]
                    ):
                        if (
                            ((match_span := url_match.span())[1] - match_span[0] + 1)
                        ) <= EMBED_CHAR_LIMITS[
                            "title"
                        ]:  # shift entire URL down
                            embed_dict["author"]["name"] = author_name[
                                : url_match.start()
                            ]
                            embed_dict["title"] = (
                                author_name[url_match.start() :]
                                + f'\n{embed_dict["title"]}'
                            ).removesuffix("\n")

                            normal_split = False

                    if normal_split:
                        embed_dict["author"]["name"] = author_name[
                            : EMBED_CHAR_LIMITS["author.name"] - 1
                        ]
                        embed_dict["title"] = (
                            author_name[EMBED_CHAR_LIMITS["author.name"] - 1 :]
                            + f'\n{embed_dict["title"]}'
                        ).removesuffix("\n")

                    if not embed_dict["title"]:
                        del embed_dict["title"]

                    updated = True

            if "title" in embed_dict:
                title = embed_dict["title"]
                if len(title) > EMBED_CHAR_LIMITS["title"]:
                    if "description" not in embed_dict:
                        embed_dict["description"] = ""

                    normal_split = True

                    if (
                        (
                            inline_code_matches := tuple(
                                re.finditer(regex_patterns.INLINE_CODE_BLOCK, title)
                            )
                        )
                        and (inline_code_match := inline_code_matches[-1]).start()
                        < EMBED_CHAR_LIMITS["title"] - 1
                        and inline_code_match.end() > EMBED_CHAR_LIMITS["title"] - 1
                    ):

                        if divide_code_blocks:
                            embed_dict[
                                "title"
                            ] = f'{title[: EMBED_CHAR_LIMITS["title"] - 1]}`'

                            embed_dict["description"] = (
                                f'`{title[EMBED_CHAR_LIMITS["title"] - 1 :]}'
                                f'\n{embed_dict["description"]}'
                            ).removesuffix("\n")
                            normal_split = False
                        elif (
                            (
                                (match_span := inline_code_match.span())[1]
                                - match_span[0]
                                + 1
                            )
                        ) <= EMBED_CHAR_LIMITS[
                            "description"
                        ]:  # move it down to the next text field
                            embed_dict["title"] = title[: inline_code_match.start()]
                            embed_dict["description"] = (
                                title[inline_code_match.start() :]
                                + f'\n{embed_dict["description"]}'
                            ).removesuffix("\n")

                            normal_split = False

                    elif (
                        (url_matches := tuple(re.finditer(regex_patterns.URL, title)))
                        and (url_match := url_matches[-1]).start()
                        < EMBED_CHAR_LIMITS["title"] - 1
                        and url_match.end() > EMBED_CHAR_LIMITS["title"]
                    ):
                        if (
                            ((match_span := url_match.span())[1] - match_span[0] + 1)
                        ) <= EMBED_CHAR_LIMITS[
                            "description"
                        ]:  # shift entire URL down
                            embed_dict["title"] = title[: url_match.start()]
                            embed_dict["description"] = (
                                title[url_match.start() :]
                                + f'\n{embed_dict["description"]}'
                            ).removesuffix("\n")
                            normal_split = False

                    if normal_split:
                        embed_dict["title"] = title[: EMBED_CHAR_LIMITS["title"] - 1]
                        embed_dict["description"] = (
                            title[EMBED_CHAR_LIMITS["title"] - 1 :]
                            + f'\n{embed_dict["description"]}'
                        ).removesuffix("\n")

                    if not embed_dict["description"]:
                        del embed_dict["description"]

                    updated = True

            if "description" in embed_dict:
                description = embed_dict["description"]
                if len(description) > EMBED_CHAR_LIMITS["description"]:
                    next_embed_dict = {
                        attr: embed_dict.pop(attr)
                        for attr in ("color", "fields", "image", "footer")
                        if attr in embed_dict
                    }
                    next_embed_dict["description"] = ""
                    if "color" in next_embed_dict:
                        embed_dict["color"] = next_embed_dict["color"]

                    normal_split = True

                    if (
                        (
                            code_matches := tuple(
                                re.finditer(regex_patterns.CODE_BLOCK, description)
                            )
                        )
                        and (code_match := code_matches[-1]).start()
                        < EMBED_CHAR_LIMITS["description"] - 1
                        and code_match.end() > EMBED_CHAR_LIMITS["description"] - 1
                    ):

                        if (
                            divide_code_blocks
                            and code_match.start() + code_match.group().find("\n")
                            < EMBED_CHAR_LIMITS["description"] - 1
                        ):  # find first newline required for a valid code block
                            embed_dict[
                                "description"
                            ] = f'{description[: EMBED_CHAR_LIMITS["description"] - 3]}```'

                            next_embed_dict["description"] = (
                                f'```{code_match.group(1)}\n{description[EMBED_CHAR_LIMITS["description"] - 3 :]}'  # group 1 is the code language
                                + f'\n{next_embed_dict["description"]}'
                            ).removesuffix("\n")
                            normal_split = False
                        elif (
                            ((match_span := code_match.span())[1] - match_span[0] + 1)
                        ) <= EMBED_CHAR_LIMITS["description"]:
                            embed_dict["description"] = description[
                                : code_match.start()
                            ]
                            next_embed_dict["description"] = (
                                description[code_match.start() :]
                                + f'\n{next_embed_dict["description"]}'
                            ).removesuffix("\n")
                            normal_split = False

                    elif (
                        (
                            inline_code_matches := tuple(
                                re.finditer(
                                    regex_patterns.INLINE_CODE_BLOCK, description
                                )
                            )
                        )
                        and (inline_code_match := inline_code_matches[-1]).start()
                        < EMBED_CHAR_LIMITS["description"] - 1
                        and inline_code_match.end()
                        > EMBED_CHAR_LIMITS["description"] - 1
                    ):

                        if divide_code_blocks:
                            embed_dict[
                                "description"
                            ] = f'{description[: EMBED_CHAR_LIMITS["description"] - 1]}`'

                            next_embed_dict["description"] = (
                                f'`{description[EMBED_CHAR_LIMITS["description"] - 1 :]}'
                                f'\n{next_embed_dict["description"]}'
                            ).removesuffix("\n")
                            normal_split = False
                        elif (
                            (
                                (match_span := inline_code_match.span())[1]
                                - match_span[0]
                                + 1
                            )
                        ) <= EMBED_CHAR_LIMITS[
                            "description"
                        ]:  # shift entire inline code block down
                            embed_dict["description"] = description[
                                : inline_code_match.start()
                            ]
                            next_embed_dict["description"] = (
                                description[inline_code_match.start() :]
                                + f'\n{next_embed_dict["description"]}'
                            ).removesuffix("\n")
                            normal_split = False

                    elif (
                        (
                            url_matches := tuple(
                                re.finditer(regex_patterns.URL, description)
                            )
                        )
                        and (url_match := url_matches[-1]).start()
                        < EMBED_CHAR_LIMITS["description"] - 1
                        and url_match.end() > EMBED_CHAR_LIMITS["description"] - 1
                    ):
                        if (
                            ((match_span := url_match.span())[1] - match_span[0] + 1)
                        ) <= EMBED_CHAR_LIMITS[
                            "description"
                        ]:  # shift entire URL down

                            embed_dict["description"] = description[: url_match.start()]
                            next_embed_dict["description"] = (
                                description[url_match.start() :]
                                + f'\n{next_embed_dict["description"]}'
                            ).removesuffix("\n")

                            normal_split = False

                    if normal_split:
                        embed_dict["description"] = description[
                            : EMBED_CHAR_LIMITS["description"] - 1
                        ]
                        next_embed_dict["description"] = (
                            description[EMBED_CHAR_LIMITS["description"] - 1 :]
                            + f'\n{next_embed_dict["description"]}'
                        ).removesuffix("\n")

                    if not next_embed_dict["description"]:
                        del next_embed_dict["description"]

                    if next_embed_dict and not (
                        len(next_embed_dict) == 1 and "color" in next_embed_dict
                    ):
                        embed_dicts.insert(i + 1, next_embed_dict)

                    updated = True

            current_len = (
                len(embed_dict.get("author", {}).get("name", ""))
                + len(embed_dict.get("title", ""))
                + len(embed_dict.get("description", ""))
            )

            if "fields" in embed_dict:
                fields = embed_dict["fields"]
                for j in range(len(fields)):
                    field = fields[j]
                    if "name" in field:
                        field_name = field["name"]
                        if len(field_name) > EMBED_CHAR_LIMITS["field.name"]:
                            if "value" not in field:
                                field["value"] = ""

                            normal_split = True

                            if (
                                inline_code_matches := tuple(
                                    re.finditer(
                                        regex_patterns.INLINE_CODE_BLOCK, field_name
                                    )
                                )
                            ) and (
                                inline_code_match := inline_code_matches[-1]
                            ).end() > EMBED_CHAR_LIMITS[
                                "field.name"
                            ] - 1:

                                if divide_code_blocks:
                                    field[
                                        "name"
                                    ] = f'{field_name[: EMBED_CHAR_LIMITS["field.name"] - 2]}`'

                                    field["value"] = (
                                        f'`{field_name[EMBED_CHAR_LIMITS["field.name"] - 2 :]}'
                                        f'\n{field["value"]}'
                                    ).removesuffix("\n")
                                    normal_split = False
                                elif (
                                    (
                                        (match_span := inline_code_match.span())[1]
                                        - match_span[0]
                                        + 1
                                    )
                                ) <= EMBED_CHAR_LIMITS[
                                    "field.value"
                                ]:  # shift entire inline code block down
                                    field["name"] = field_name[
                                        : inline_code_match.start()
                                    ]
                                    field["value"] = (
                                        field_name[inline_code_match.start() :]
                                        + f'\n{field["value"]}'
                                    ).removesuffix("\n")
                                    normal_split = False

                            elif (
                                (
                                    url_matches := tuple(
                                        re.finditer(regex_patterns.URL, field_name)
                                    )
                                )
                                and (url_match := url_matches[-1]).start()
                                < EMBED_CHAR_LIMITS["field.name"] - 1
                                and url_match.end() > EMBED_CHAR_LIMITS["field.name"]
                            ):
                                if (
                                    (
                                        (match_span := url_match.span())[1]
                                        - match_span[0]
                                        + 1
                                    )
                                ) <= EMBED_CHAR_LIMITS[
                                    "field.name"
                                ]:  # shift entire URL down
                                    field["name"] = field_name[: url_match.start()]
                                    field["value"] = (
                                        field_name[url_match.start() :]
                                        + f'\n{field["value"]}'
                                    ).removesuffix("\n")

                                    normal_split = False

                            if normal_split:
                                field["name"] = field_name[
                                    : EMBED_CHAR_LIMITS["field.name"] - 1
                                ]
                                field["value"] = (
                                    field_name[EMBED_CHAR_LIMITS["field.name"] - 1 :]
                                    + f'\n{field["value"]}'
                                ).removesuffix("\n")

                            if not field["value"]:
                                del field["value"]

                            updated = True

                    if "value" in field:
                        field_value = field["value"]
                        if len(field_value) > EMBED_CHAR_LIMITS["field.value"]:
                            next_field = {}
                            next_field["name"] = "\u200b"

                            if "inline" in field:
                                next_field["inline"] = field["inline"]

                            normal_split = True

                            if (
                                (
                                    code_matches := tuple(
                                        re.finditer(
                                            regex_patterns.CODE_BLOCK, field_value
                                        )
                                    )
                                )
                                and (code_match := code_matches[-1]).start()
                                < EMBED_CHAR_LIMITS["field.value"] - 1
                                and code_match.end()
                                > EMBED_CHAR_LIMITS["field.value"] - 1
                            ):

                                if (
                                    divide_code_blocks
                                    and code_match.start()
                                    + code_match.group().find("\n")
                                    < EMBED_CHAR_LIMITS["field.value"] - 1
                                ):  # find first newline required for a valid code block
                                    field[
                                        "value"
                                    ] = f'{field_value[: EMBED_CHAR_LIMITS["field.value"] - 3]}```'

                                    next_field["value"] = (
                                        f'```{code_match.group(1)}\n{field_value[EMBED_CHAR_LIMITS["field.value"] - 3 :]}'  # group 1 is the code language
                                        f'\n{next_field["field.value"]}'
                                    ).removesuffix("\n")
                                    normal_split = False
                                elif (
                                    (
                                        (match_span := code_match.span())[1]
                                        - match_span[0]
                                        + 1
                                    )
                                ) <= EMBED_CHAR_LIMITS["field.value"]:
                                    field["value"] = field_value[: code_match.start()]
                                    next_field["value"] = (
                                        field_value[code_match.start() :]
                                        + f'\n{next_field["value"]}'
                                    ).removesuffix("\n")
                                    normal_split = False

                            elif (
                                (
                                    inline_code_matches := tuple(
                                        re.finditer(
                                            regex_patterns.INLINE_CODE_BLOCK,
                                            field_value,
                                        )
                                    )
                                )
                                and (
                                    inline_code_match := inline_code_matches[-1]
                                ).start()
                                < EMBED_CHAR_LIMITS["field.value"] - 1
                                and inline_code_match.end()
                                > EMBED_CHAR_LIMITS["field.value"] - 1
                            ):

                                if divide_code_blocks:
                                    field[
                                        "value"
                                    ] = f'{field_value[: EMBED_CHAR_LIMITS["field.value"] - 1]}`'

                                    next_field["value"] = (
                                        f'`{field_value[EMBED_CHAR_LIMITS["field.value"] - 1 :]}'
                                        f'\n{next_field["value"]}'
                                    ).removesuffix("\n")
                                    normal_split = False
                                elif (
                                    (
                                        (match_span := inline_code_match.span())[1]
                                        - match_span[0]
                                        + 1
                                    )
                                ) <= EMBED_CHAR_LIMITS[
                                    "field.value"
                                ]:  # shift entire inline code block down
                                    field["value"] = field_value[
                                        : inline_code_match.start()
                                    ]
                                    next_field["value"] = (
                                        field_value[inline_code_match.start() :]
                                        + f'\n{next_field["value"]}'
                                    ).removesuffix("\n")
                                    normal_split = False

                            elif (
                                (
                                    url_matches := tuple(
                                        re.finditer(regex_patterns.URL, field_value)
                                    )
                                )
                                and (url_match := url_matches[-1]).start()
                                < EMBED_CHAR_LIMITS["field.value"] - 1
                                and url_match.end() > EMBED_CHAR_LIMITS["field.value"]
                            ):
                                if (
                                    (
                                        (match_span := url_match.span())[1]
                                        - match_span[0]
                                        + 1
                                    )
                                ) <= EMBED_CHAR_LIMITS[
                                    "field.value"
                                ]:  # shift entire URL down
                                    field["value"] = field_value[: url_match.start()]
                                    next_field["value"] = (
                                        field_value[url_match.start() :]
                                        + f'\n{next_field["value"]}'
                                    ).removesuffix("\n")

                                    normal_split = False

                            if normal_split:
                                field["value"] = field_value[
                                    : EMBED_CHAR_LIMITS["field.value"] - 1
                                ]
                                next_field["value"] = (
                                    field["value"][
                                        EMBED_CHAR_LIMITS["field.value"] - 1 :
                                    ]
                                    + f'\n{next_field["value"]}'
                                ).removesuffix("\n")

                            if not next_field["value"]:
                                del next_field["value"]

                            if next_field:
                                fields.insert(j + 1, next_field)

                            updated = True

                for j in range(len(fields)):
                    field = fields[j]
                    field_char_count = len(field.get("name", "")) + len(
                        field.get("value", "")
                    )
                    if (
                        current_len + field_char_count > EMBED_TOTAL_CHAR_LIMIT
                        or j > 24
                    ):
                        next_embed_dict = {
                            attr: embed_dict.pop(attr)
                            for attr in ("color", "image", "footer")
                            if attr in embed_dict
                        }
                        if "color" in next_embed_dict:
                            embed_dict["color"] = next_embed_dict["color"]

                        embed_dict["fields"] = fields[:j]
                        next_embed_dict["fields"] = fields[j:]
                        embed_dicts.insert(i + 1, next_embed_dict)

                        updated = True
                        break

                    current_len += field_char_count

            if "footer" in embed_dict and "text" in embed_dict["footer"]:
                footer_text = ""
                for _ in range(2):
                    footer_text = embed_dict["footer"]["text"]
                    footer_text_len = len(footer_text)
                    if (
                        footer_text_len > EMBED_CHAR_LIMITS["footer.text"]
                        or current_len + footer_text_len > EMBED_TOTAL_CHAR_LIMIT
                    ):
                        if i + 1 < len(embed_dicts):
                            next_embed_dict = embed_dicts[i + 1]
                        else:
                            next_embed_dict = {
                                "footer": {
                                    attr: embed_dict["footer"].pop(attr)
                                    for attr in ("icon_url", "proxy_icon_url")
                                    if attr in embed_dict["footer"]
                                }
                            }
                            if "color" in embed_dict:
                                next_embed_dict["color"] = embed_dict["color"]

                            embed_dicts.insert(i + 1, next_embed_dict)

                        if footer_text_len > EMBED_CHAR_LIMITS["footer.text"]:
                            split_index = EMBED_CHAR_LIMITS["footer.text"] - 1
                        else:
                            split_index = (
                                footer_text_len
                                - (
                                    current_len
                                    + footer_text_len
                                    - EMBED_TOTAL_CHAR_LIMIT
                                )
                                - 1
                            )

                        normal_split = True

                        if (
                            (
                                url_matches := tuple(
                                    re.finditer(regex_patterns.URL, footer_text)
                                )
                            )
                            and (url_match := url_matches[-1]).start() < split_index
                            and url_match.end() > split_index
                        ):
                            if (
                                (
                                    (match_span := url_match.span())[1]
                                    - match_span[0]
                                    + 1
                                )
                            ) <= EMBED_CHAR_LIMITS[
                                "footer.text"
                            ]:  # shift entire URL down
                                embed_dict["footer"]["text"] = footer_text[
                                    : url_match.start()
                                ]
                                next_embed_dict["footer"]["text"] = (
                                    footer_text[url_match.start() :]
                                    + f'\n{next_embed_dict["footer"]["text"]}'
                                ).removesuffix("\n")
                                normal_split = False

                        if normal_split:
                            embed_dict["footer"]["text"] = footer_text[:split_index]
                            next_embed_dict["footer"]["text"] = (
                                footer_text[split_index:]
                                + f'\n{next_embed_dict["footer"]["text"]}'
                            ).removesuffix("\n")

                        if not embed_dict["footer"]["text"]:
                            del embed_dict["footer"]["text"]

                        if next_embed_dict["footer"]:
                            embed_dicts.insert(i + 1, next_embed_dict)

                        updated = True

                    current_len += len(footer_text)

    return embed_dicts


def check_embed_dict_char_count(embed_dict: Mapping[str, Any]) -> int:
    """Count the number of characters in the text fields of an embed dictionary.

    Parameters
    ----------
    embed_dict : Mapping[str, Any]
        The target embed dictionary.

    Returns
    -------
    int
        The character count.
    """
    count = 0

    if (author := embed_dict.get("author")) is not None:
        count += len(author.get("name", ""))

    count += len(embed_dict.get("title", "")) + len(embed_dict.get("description", ""))

    fields = embed_dict.get("fields", ())

    for field in fields:
        count += len(field.get("name", "")) + len(field.get("value", ""))

    if (footer := embed_dict.get("footer")) is not None:
        count += len(footer.get("text", ""))

    return count


def validate_embed_dict_char_count(embed_dict: Mapping[str, Any]) -> bool:
    """Check if all text attributes of an embed dictionary are below their respective
    character limits.

    Parameters
    ----------
    embed_dict : Mappint[str, Any]
        The target embed dictionary.

    Returns
    -------
    bool
        The result.
    """

    count = 0

    author = embed_dict.get("author")
    if author is not None:
        author_name_count = len(author.get("name", ""))
        if author_name_count > EMBED_CHAR_LIMITS["author.name"]:
            return False
        count += author_name_count

    title_count = len(embed_dict.get("title", ""))
    if title_count > EMBED_CHAR_LIMITS["title"]:
        return False

    count += title_count

    description_count = len(embed_dict.get("description", ""))
    if description_count > EMBED_CHAR_LIMITS["description"]:
        return False

    count += description_count

    fields = embed_dict.get("fields", [])

    if len(fields) > EMBED_FIELDS_LIMIT:
        return False

    for field in fields:
        field_name_count = len(field.get("name", ""))
        field_value_count = len(field.get("value", ""))

        if (
            field_name_count > EMBED_CHAR_LIMITS["field.name"]
            or field_value_count > EMBED_CHAR_LIMITS["field.value"]
        ):
            return False

        count += field_name_count + field_value_count

    footer = embed_dict.get("footer")
    if footer is not None:
        footer_text_count = len(footer.get("text", ""))

        if footer_text_count > EMBED_CHAR_LIMITS["footer.text"]:
            return False

        count += footer_text_count

    return count <= EMBED_TOTAL_CHAR_LIMIT


def validate_embed_dict(embed_dict: Mapping[str, Any]) -> bool:
    """Checks if an embed dictionary can produce
    a viable embed on Discord. This also includes keeping to character limits on all
    embed attributes.

    Parameters
    ----------
    embed_dict : Mapping[str, Any]
        The target embed dictionary.

    Returns
    -------
    bool
        A boolean indicating the validity of the
        given input embed dictionary.

    """
    if not embed_dict or not isinstance(embed_dict, dict):
        return False

    embed_dict_len = len(embed_dict)

    if (
        embed_dict_len == 1
        and ("color" in embed_dict or "timestamp" in embed_dict)
        or embed_dict_len == 2
        and ("color" in embed_dict and "timestamp" in embed_dict)
    ):
        return False

    for k, v in embed_dict.items():
        if (
            not isinstance(k, str)
            or k in ("title", "description")
            and (not isinstance(v, str))
            or k in ("author", "thumbnail", "image", "footer")
            and (not isinstance(v, dict))
            or k in ("thumbnail", "image")
            and ("url" not in v or not isinstance(v["url"], str) or not v["url"])  # type: ignore
            or k == "author"
            and (
                "name" not in v
                or any(
                    ak in v and (not isinstance(v[ak], str) or not v[ak])  # type: ignore
                    for ak in ("name", "url", "icon_url")
                )
            )
            or k == "footer"
            and (
                "text" not in v
                or any(
                    ak in v and (not isinstance(v[ak], str) or not v[ak])  # type: ignore
                    for ak in ("text", "icon_url")
                )
            )
            or k == "color"
            and (not isinstance(v, int) or not 0 <= embed_dict["color"] <= 0xFFFFFF)
            or k == "fields"
            and (
                not isinstance(v, list)
                or isinstance(v, list)
                and any(
                    (
                        not isinstance(d, dict)
                        or ("name" not in d or "value" not in d)
                        or (
                            not isinstance(d["name"], str)
                            or not d["name"]
                            or not isinstance(d["value"], str)
                            or not d["value"]
                        )
                        or "inline" in d
                        and not isinstance(d["inline"], bool)
                    )
                    for d in v
                )
            )
        ):
            return False

        elif k == "timestamp":
            if not isinstance(v, str):
                return False
            try:
                datetime.datetime.fromisoformat(embed_dict[k])
            except ValueError:
                return False

    return validate_embed_dict_char_count(embed_dict)


@overload
def filter_embed_dict(embed_dict: dict[str, Any]) -> None:
    ...


@overload
def filter_embed_dict(
    embed_dict: dict[str, Any], in_place: bool = True
) -> dict[str, Any]:
    ...


def filter_embed_dict(
    embed_dict: dict[str, Any], in_place: bool = True
) -> Optional[dict[str, Any]]:
    """Delete invalid embed attributes in the given embed dictionary that would cause
    exceptionsfor structural errors. Note that the output embed dictionary of this
    function might still not be a viable embed dictionary to be sent to Discord's
    servers.

    Parameters
    ----------
    embed_dict : dict[str, Any]
        The target embed dictionary.
    in_place : bool, optional
        Whether to do this operation on the given embed
        dictionary "in place" and to return `None` instead of a new dictionary.
         Defaults to True.

    Returns
    -------
    Optional[dict[str, Any]]
        A new filtered embed dictionary or `None` depending on the given arguments.
    """

    if not in_place:
        embed_dict = copy_embed_dict(embed_dict)

    if not embed_dict or not isinstance(embed_dict, dict):
        return None

    embed_dict_len = len(embed_dict)

    if (
        embed_dict_len == 1
        and ("color" in embed_dict or "timestamp" in embed_dict)
        or embed_dict_len == 2
        and ("color" in embed_dict and "timestamp" in embed_dict)
    ):
        return {}

    for k, v in tuple(embed_dict.items()):
        if (
            not isinstance(k, str)
            or k in ("title", "description")
            and (not isinstance(v, str))
            or k in ("author", "thumbnail", "image", "footer")
            and (
                not isinstance(v, dict)
                or k in ("thumbnail", "image")
                and ("url" not in v or not isinstance(v["url"], str) or not v["url"])
            )
            or k == "author"
            and (
                "name" not in v
                or any(
                    ak in v and (not isinstance(v[ak], str) or not v[ak])  # type: ignore
                    for ak in ("name", "url", "icon_url")
                )
            )
            or k == "footer"
            and (
                "text" not in v
                or any(
                    ak in v and (not isinstance(v[ak], str) or not v[ak])  # type: ignore
                    for ak in ("text", "icon_url")
                )
            )
            or k == "color"
            and (not isinstance(v, int) or not 0 <= embed_dict["color"] <= 0xFFFFFF)
        ):
            del embed_dict[k]

        elif k == "fields":
            if not isinstance(v, list):
                del embed_dict[k]

            for i, f in reversed(tuple(enumerate(v))):  # type: ignore
                if (
                    not isinstance(f, dict)
                    or ("name" not in f or "value" not in f)
                    or (
                        not isinstance(f["name"], str)
                        or not f["name"]
                        or not isinstance(f["value"], str)
                        or not f["value"]
                    )
                    or "inline" in f
                    and not isinstance(f["inline"], bool)
                ):
                    v.pop(i)  # type: ignore

        elif k == "timestamp":
            if not isinstance(v, str):
                return None
            try:
                datetime.datetime.fromisoformat(embed_dict[k])
            except ValueError:
                del embed_dict[k]

    if not in_place:
        return embed_dict

    return None


@overload
def handle_embed_dict_timestamp(
    embed_dict: dict[str, Any],
) -> None:
    ...


@overload
def handle_embed_dict_timestamp(
    embed_dict: dict[str, Any], *, in_place: bool = True
) -> dict[str, Any]:
    ...


def handle_embed_dict_timestamp(
    embed_dict: dict[str, Any], *, in_place: bool = True
) -> Optional[dict[str, Any]]:
    """Correct or delete the `"timestamp"` key's value in an embed dictionary.

    Parameters
    ----------
    embed_dict : dict
        The embed dictionary.
    in_place : bool, optional
        Whether to do this operation on the given embed
        dictionary "in place" and to return `None` instead of a new dictionary.
         Defaults to True.

    Returns
    -------
    Optional[dict[str, Any]]
        A new embed dictionary, depending on which arguments were given.
    """

    if not in_place:
        embed_dict = copy_embed_dict(embed_dict)

    if "timestamp" in embed_dict:
        timestamp = embed_dict["timestamp"]
        if isinstance(timestamp, str):
            try:
                final_timestamp = timestamp.removesuffix("Z")
                datetime.datetime.fromisoformat(final_timestamp)
                embed_dict["timestamp"] = final_timestamp
            except ValueError:
                del embed_dict["timestamp"]
        elif isinstance(timestamp, datetime.datetime):
            embed_dict["timestamp"] = timestamp.isoformat()
        else:
            del embed_dict["timestamp"]

    if not in_place:
        return embed_dict

    return


def copy_embed_dict(embed_dict: Mapping[str, Any]) -> dict[str, Any]:
    """Make a shallow copy of the given embed dictionary,
    and embed fields (if present).

    Parameters
    ----------
    embed_dict : Mapping[str, Any]
        The target embed dictionary.

    Returns
    -------
        dict: The copy.
    """
    # prevents shared reference bugs to attributes shared by the outputs of
    # discord.Embed.to_dict()
    copied_embed_dict = {
        k: v.copy() if isinstance(v, dict) else v for k, v in embed_dict.items()
    }

    if "fields" in embed_dict:
        copied_embed_dict["fields"] = [
            dict(field_dict) for field_dict in embed_dict["fields"]
        ]
    return copied_embed_dict


def parse_embed_field_strings(
    *strings: str,
) -> list[dict[str, Any]]:
    """Extract embed field string syntax from the given string(s).
    Syntax of an embed field string: `<name|value[|inline]>`.

    Parameters
    ----------
    *strings : str
        The target strings to extract from.

    Returns
    -------
    list[dict[str, Any]]:
        A list of embed field dictionaries with keys `"name"`, `"value"` and `"inline"`.
    """
    # syntax: <name|value[|inline=False]>
    field_regex = r"(<.*\|.*(\|True|\|False|\|1|\|0|)>)"
    field_datas = []
    true_bool_strings = ("", "true", "1")

    for string in strings:
        field_list = re.split(field_regex, string)
        for field in field_list:
            if field:
                field = field.strip()[1:-1]  # remove < and >
                field_data = field.split("|")

                if len(field_data) not in (2, 3):
                    continue
                elif len(field_data) == 2:
                    field_data.append("")

                field_data[2] = (  # type: ignore
                    True if field_data[2].lower() in true_bool_strings else False
                )

                field_datas.append(
                    {
                        "name": field_data[0],
                        "value": field_data[1],
                        "inline": field_data[2],
                    }
                )

    return field_datas


def parse_condensed_embed_list(embed_list: Union[list, tuple]) -> FlattenedEmbedDict:
    """Parses the condensed embed list syntax used in some embed creation
    commands. The syntax is:
    ```py
    [
        'author.name' or ('author.name', 'author.url') or ('author.name', 'author.url', 'icon.url'),   # embed author

        'title' or ('title', 'url') or ('title', 'url', 'thumbnail.url'),  #embed title, url, thumbnail

        '''desc.''' or ('''desc.''', 'image.url'),  # embed description, image

        0xabcdef, # or -1 for default embed color

        [   # embed fields
        '''
        <field.name|
        ...field.value....
        |field.inline>
        ''',
        ],

        'footer.text' or ('footer.text', 'footer.icon_url'),   # embed footer

        datetime(year, month, day[, hour[, minute[, second[, microsecond]]]]) or '2021-04-17T17:36:00.553' # embed timestamp
    ]
    ```

    The list must contain at least 1 element.
    """
    arg_count = len(embed_list)

    embed_args = {}

    if arg_count > 0:
        if isinstance(embed_list[0], (tuple, list)):
            if len(embed_list[0]) == 3:
                embed_args.update(
                    author_name=embed_list[0][0] + "",
                    author_url=embed_list[0][0] + "",
                    author_icon_url=embed_list[0][2] + "",
                )
            elif len(embed_list[0]) == 2:
                embed_args.update(
                    author_name=embed_list[0][0] + "",
                    author_url=embed_list[0][1] + "",
                )
            elif len(embed_list[0]) == 1:
                embed_args.update(
                    author_name=embed_list[0][0] + "",
                )

        else:
            embed_args.update(
                author_name=embed_list[0] + "",
            )
    else:
        raise ValueError(
            f"Invalid arguments! The condensed embed syntax is: ```\n{CONDENSED_EMBED_DATA_LIST_SYNTAX}\n```"
        )

    if arg_count > 1:
        if isinstance(embed_list[1], (tuple, list)):
            if len(embed_list[1]) == 3:
                embed_args.update(
                    title=embed_list[1][0] + "",
                    url=embed_list[1][1] + "",
                    thumbnail_url=embed_list[1][2] + "",
                )

            elif len(embed_list[1]) == 2:
                embed_args.update(
                    title=embed_list[1][0] + "",
                    url=embed_list[1][1] + "",
                )

            elif len(embed_list[1]) == 1:
                embed_args.update(
                    title=embed_list[1][0] + "",
                )

        else:
            embed_args.update(
                title=embed_list[1] + "",
            )

    if arg_count > 2:
        if isinstance(embed_list[2], (tuple, list)):
            if len(embed_list[2]) == 2:
                embed_args.update(
                    description=embed_list[2][0] + "",
                    image_url=embed_list[2][1] + "",
                )

            elif len(embed_list[2]) == 1:
                embed_args.update(
                    description=embed_list[2][0] + "",
                )

        else:
            embed_args.update(
                description=embed_list[2] + "",
            )

    if arg_count > 3:
        if embed_list[3] > -1:
            embed_args.update(
                color=embed_list[3] + 0,
            )

    if arg_count > 4:
        try:
            fields = parse_embed_field_strings(*embed_list[4])
            embed_args.update(fields=fields)
        except TypeError:
            raise ValueError(
                "Invalid format for field string(s) in the condensed embed syntax!"
                'The format should be `"<name|value|inline>"`'
            )

    if arg_count > 5:
        if isinstance(embed_list[5], (tuple, list)):
            if len(embed_list[5]) == 2:
                embed_args.update(
                    footer_text=embed_list[5][0] + "",
                    footer_icon_url=embed_list[5][1] + "",
                )

            elif len(embed_list[5]) == 1:
                embed_args.update(
                    footer_text=embed_list[5][0] + "",
                )

        else:
            embed_args.update(
                footer_text=embed_list[5] + "",
            )

    if arg_count > 6:
        embed_args.update(timestamp=embed_list[6] + "")

    return embed_args  # type: ignore


def create_embed_as_dict(
    author_name: Optional[str] = None,
    author_url: Optional[str] = None,
    author_icon_url: Optional[str] = None,
    title: Optional[str] = None,
    url: Optional[str] = None,
    thumbnail_url: Optional[str] = None,
    description: Optional[str] = None,
    image_url: Optional[str] = None,
    color: int = 0,
    fields: Optional[
        Sequence[Union[list[Union[str, bool]], tuple[str, str], tuple[str, str, bool]]]
    ] = None,
    footer_text: Optional[str] = None,
    footer_icon_url: Optional[str] = None,
    timestamp: Optional[Union[str, datetime.datetime]] = None,
) -> dict[str, Any]:

    embed_dict = {}

    if author_name:
        embed_dict["author"] = {"name": author_name}
        if author_url:
            embed_dict["author"]["url"] = author_url
        if author_icon_url:
            embed_dict["author"]["icon_url"] = author_icon_url

    if footer_text:
        embed_dict["footer"] = {"text": footer_text}
        if footer_icon_url:
            embed_dict["footer"]["icon_url"] = footer_icon_url

    if title:
        embed_dict["title"] = title

    if url:
        embed_dict["url"] = url

    if description:
        embed_dict["description"] = description

    embed_dict["color"] = int(color) if 0 <= color <= 0xFFFFFF else 0

    if timestamp:
        if isinstance(timestamp, str):
            try:
                datetime.datetime.fromisoformat(timestamp.removesuffix("Z"))
                embed_dict["timestamp"] = timestamp
            except ValueError:
                pass
        elif isinstance(timestamp, datetime.datetime):
            embed_dict["timestamp"] = timestamp.isoformat()

    if image_url:
        embed_dict["image"] = {"url": image_url}

    if thumbnail_url:
        embed_dict["thumbnail"] = {"url": thumbnail_url}

    if fields:
        fields_list = []
        embed_dict["fields"] = fields_list
        for i, field in enumerate(fields):
            name, value, inline = _read_embed_field_dict(field_dict=field, index=i)  # type: ignore
            fields_list.append({"name": name, "value": value, "inline": inline})

    return embed_dict


def create_embed(
    *,
    author_name: Optional[str] = None,
    author_url: Optional[str] = None,
    author_icon_url: Optional[str] = None,
    title: Optional[str] = None,
    url: Optional[str] = None,
    thumbnail_url: Optional[str] = None,
    description: Optional[str] = None,
    image_url: Optional[str] = None,
    color: int = 0,
    fields: Optional[
        Sequence[Union[list[Union[str, bool]], tuple[str, str], tuple[str, str, bool]]]
    ] = None,
    footer_text: Optional[str] = None,
    footer_icon_url: Optional[str] = None,
    timestamp: Optional[Union[str, datetime.datetime]] = None,
) -> discord.Embed:
    """Create an embed using the specified arguments.

    Parameters
    ----------
        author_name (Optional[str], optional): The value for `author.name`.
          Defaults to None.
        author_url (Optional[str], optional): The value for `author.url`.
          Defaults to None.
        author_icon_url (Optional[str], optional): The value for `author.icon_url`.
          Defaults to None.
        title (Optional[str], optional): The value for `title`.
          Defaults to None.
        url (Optional[str], optional): The value for `url`.
          Defaults to None.
        thumbnail_url (Optional[str], optional): The value for `thumbnail_url`.
          Defaults to None.
        description (Optional[str], optional): The value for `description`.
          Defaults to None.
        image_url (Optional[str], optional): The value for `image.url`.
          Defaults to None.
        color (int, optional): The value for `color`.
          Defaults to 0.
        fields (Optional[
                Sequence[Union[list[Union[str, bool]], tuple[str, str, bool]]]]
          , optional):
          The value for `fields`, which must be a sequence of embed fields.
          Those can be an embed field dictionary or a 3-item list/tuple of
          values for `fields.N.name`, `fields.N.value` and `fields.N.inline`.
          Defaults to None.
        footer_text (Optional[str], optional): The value for `footer.text`.
          Defaults to None.
        footer_icon_url (Optional[str], optional): The value for `footer.icon_url`.
          Defaults to None.
        timestamp (Optional[Union[str, datetime.datetime]], optional): The value for
          `timestamp`. Defaults to None.

    Returns
    -------
        Embed: The created embed.

    Raises
    ------
        TypeError
            invalid argument types.
    """
    embed = discord.Embed(
        title=title,
        url=url,
        description=description,
        color=color if 0 <= color <= 0xFFFFFF else 0,
    )

    if timestamp:
        if isinstance(timestamp, str):
            try:
                embed.timestamp = datetime.datetime.fromisoformat(
                    timestamp.removesuffix("Z")
                )
            except ValueError:
                pass
        elif isinstance(timestamp, datetime.datetime):
            embed.timestamp = timestamp
        else:
            raise TypeError(
                "argument 'timestamp' must be None or a string or datetime object"
            )

    if author_name:
        embed.set_author(name=author_name, url=author_url, icon_url=author_icon_url)

    if thumbnail_url:
        embed.set_thumbnail(url=thumbnail_url)

    if image_url:
        embed.set_image(url=image_url)

    if fields:
        for i, field in enumerate(fields):
            name, value, inline = _read_embed_field_dict(field_dict=field, index=i)  # type: ignore
            embed.add_field(
                name=name,
                value=value,
                inline=inline or False,
            )

    if footer_text:
        embed.set_footer(text=footer_text, icon_url=footer_icon_url)

    return embed


def edit_embed(
    embed: discord.Embed,
    in_place: bool = True,
    edit_inner_fields: bool = False,
    *,
    author_name: Optional[str] = None,
    author_url: Optional[str] = None,
    author_icon_url: Optional[str] = None,
    title: Optional[str] = None,
    url: Optional[str] = None,
    thumbnail_url: Optional[str] = None,
    description: Optional[str] = None,
    image_url: Optional[str] = None,
    color: int = -1,
    fields: Optional[
        Sequence[Union[list[Union[str, bool]], tuple[str, str], tuple[str, str, bool]]]
    ] = None,
    footer_text: Optional[str] = None,
    footer_icon_url: Optional[str] = None,
    timestamp: Optional[Union[str, datetime.datetime]] = None,
) -> Optional[discord.Embed]:

    """Edit a given embed using the specified arguments.

    Parameters
    ----------
        embed (discord.Embed): The target embed.
        in_place (bool, optional): Whether to do this operation on the given embed
          "in place" and to return `None` instead of a new embed.
          Defaults to True.
        edit_inner_fields (bool, optional): Whether to use the given embed
          fields to edit existing embed fields present in the given embed,
          by only changing what was supplied. If set to `True` and there are
          more input embed fields than in the target embed, those will be added
          as new embed fields. Note that the structure of those fields must be
          correct to avoid errors.
        author_name (Optional[str], optional): The value for `author.name`.
          Defaults to None.
        author_url (Optional[str], optional): The value for `author.url`.
          Defaults to None.
        author_icon_url (Optional[str], optional): The value for `author.icon_url`.
          Defaults to None.
        title (Optional[str], optional): The value for `title`.
          Defaults to None.
        url (Optional[str], optional): The value for `url`.
          Defaults to None.
        thumbnail_url (Optional[str], optional): The value for `thumbnail_url`.
          Defaults to None.
        description (Optional[str], optional): The value for `description`.
          Defaults to None.
        image_url (Optional[str], optional): The value for `image.url`.
          Defaults to None.
        color (int, optional): The value for `color`.
          Defaults to 0.
        fields (Optional[
                Sequence[Union[list[Union[str, bool]], tuple[str, str, bool]]]]
          , optional):
          The value for `fields`, which must be a sequence of embed fields.
          Those can be an embed field dictionary or a 3-item list/tuple of
          values for `fields.N.name`, `fields.N.value` and `fields.N.inline`.
          Defaults to None.
        footer_text (Optional[str], optional): The value for `footer.text`.
          Defaults to None.
        footer_icon_url (Optional[str], optional): The value for `footer.icon_url`.
          Defaults to None.
        timestamp (Optional[Union[str, datetime.datetime]], optional): The value for
          `timestamp`. Defaults to None.

    Returns
    -------
        Optional[discord.Embed]: A new embed with edits applied or `None`.

    Raises
    ------
        ValueError
            Invalid argument structure.
        TypeError
            Invalid argument type.
    """

    if in_place:
        if title is not None:
            embed.title = title

        if url is not None:
            embed.url = url

        if description is not None:
            embed.description = description

        if 0 <= color <= 0xFFFFFF:
            embed.color = color

        if timestamp is not None:
            if isinstance(timestamp, str):
                try:
                    embed.timestamp = datetime.datetime.fromisoformat(
                        timestamp.removesuffix("Z")
                    )
                except ValueError:
                    pass
            elif isinstance(timestamp, datetime.datetime):
                embed.timestamp = timestamp
            else:
                raise TypeError(
                    "argument 'timestamp' must be None or a string or datetime object"
                )

        if author_name is not None:
            auth_name = author_name
            auth_url = author_url if author_url is not None else embed.author.url
            auth_icon_url = (
                author_icon_url
                if author_icon_url is not None
                else embed.author.icon_url
            )

            embed.set_author(name=auth_name, url=auth_url, icon_url=auth_icon_url)

        if thumbnail_url is not None:
            embed.set_thumbnail(url=thumbnail_url)

        if image_url is not None:
            embed.set_image(url=image_url)

        embed_fields = embed.fields
        embed_field_count = len(embed_fields)

        if fields is not None:
            for i, field in enumerate(fields):
                if i < embed_field_count and edit_inner_fields:
                    embed_field = embed_fields[i]

                    name = embed_field.name
                    value = embed_field.value
                    inline = embed_field.inline

                    name, value, inline = _read_embed_field_dict(
                        field_dict=field, index=i  # type: ignore
                    )
                    embed.set_field_at(
                        i,
                        name=name,
                        value=value,
                        inline=inline or False,
                    )

                else:
                    name = value = inline = None
                    if isinstance(field, dict):
                        name, value, inline = (
                            field.get("name"),
                            field.get("value"),
                            field.get("inline", True),
                        )
                    elif isinstance(field, (list, tuple)):
                        name, value, *overflow = field
                        if overflow:
                            inline = overflow[0]

                    else:
                        raise TypeError(
                            f" invalid embed field type at `fields[{i}]`: an embed "
                            "field must be a list/tuple of the structure "
                            "(str, str, bool) or a dictionary with the keys "
                            "'name', 'value', inline' containing values of those "
                            "same types "
                        )

                    if (
                        not isinstance(name, str)
                        or not isinstance(value, str)
                        or not isinstance(inline, bool)
                    ):
                        raise ValueError(
                            f" invalid embed field at `fields[{i}]`: an embed "
                            "field must be a list/tuple of the structure "
                            "(str, str, bool) or a dictionary with the keys "
                            "'name', 'value', inline' containing the same types "
                            "of values"
                        )

                    embed.add_field(
                        name=name,
                        value=value,
                        inline=inline or False,
                    )

        if footer_text is not None:
            embed.set_footer(text=footer_text, icon_url=footer_icon_url)

    else:
        old_embed_dict: dict[str, Any] = embed.to_dict()  # type: ignore
        update_embed_dict = create_embed_as_dict(
            author_name=author_name,
            author_url=author_url,
            author_icon_url=author_icon_url,
            title=title,
            url=url,
            thumbnail_url=thumbnail_url,
            description=description,
            image_url=image_url,
            color=color,
            fields=fields,
            footer_text=footer_text,
            footer_icon_url=footer_icon_url,
            timestamp=timestamp,
        )

        if edit_inner_fields:
            if "fields" in old_embed_dict:
                old_embed_dict["fields"] = {  # type: ignore
                    str(i): old_embed_dict["fields"][i]
                    for i in range(len(old_embed_dict["fields"]))
                }
            if "fields" in update_embed_dict:
                update_embed_dict["fields"] = {
                    str(i): update_embed_dict["fields"][i]
                    for i in range(len(update_embed_dict["fields"]))
                }

        recursive_mapping_update(old_embed_dict, update_embed_dict, add_new_keys=True)  # type: ignore

        if edit_inner_fields:
            if "fields" in old_embed_dict:
                old_embed_dict["fields"] = [
                    old_embed_dict["fields"][i]
                    for i in sorted(old_embed_dict["fields"].keys())  # type: ignore
                ]
            if "fields" in update_embed_dict:
                update_embed_dict["fields"] = [
                    update_embed_dict["fields"][i]
                    for i in sorted(update_embed_dict["fields"].keys())
                ]

        return discord.Embed.from_dict(old_embed_dict)


async def send_embed(
    channel: discord.abc.Messageable,
    *,
    author_name: Optional[str] = None,
    author_url: Optional[str] = None,
    author_icon_url: Optional[str] = None,
    title: Optional[str] = None,
    url: Optional[str] = None,
    thumbnail_url: Optional[str] = None,
    description: Optional[str] = None,
    image_url: Optional[str] = None,
    color: int = 0,
    fields: Optional[
        Sequence[Union[list[Union[str, bool]], tuple[str, str], tuple[str, str, bool]]]
    ] = None,
    footer_text: Optional[str] = None,
    footer_icon_url: Optional[str] = None,
    timestamp: Optional[Union[str, datetime.datetime]] = None,
    reference: Optional[
        Union[discord.Message, discord.MessageReference, discord.PartialMessage]
    ] = None,
) -> discord.Message:
    """Create an embed using the given arguments and send it to a
    `discord.abc.Messageable` and return the resulting message.

    Parameters
    ----------
        channel (discord.abc.Messageable): The messageable object to send
          an embed into.
        author_name (Optional[str], optional): The value for `author.name`.
          Defaults to None.
        author_url (Optional[str], optional): The value for `author.url`.
          Defaults to None.
        author_icon_url (Optional[str], optional): The value for `author.icon_url`.
          Defaults to None.
        title (Optional[str], optional): The value for `title`.
          Defaults to None.
        url (Optional[str], optional): The value for `url`.
          Defaults to None.
        thumbnail_url (Optional[str], optional): The value for `thumbnail_url`.
          Defaults to None.
        description (Optional[str], optional): The value for `description`.
          Defaults to None.
        image_url (Optional[str], optional): The value for `image.url`.
          Defaults to None.
        color (int, optional): The value for `color`.
          Defaults to 0.
        fields (Optional[
                Sequence[Union[list[Union[str, bool]], tuple[str, str, bool]]]]
          , optional):
          The value for `fields`, which must be a sequence of embed fields.
          Those can be an embed field dictionary or a 3-item list/tuple of
          values for `fields.N.name`, `fields.N.value` and `fields.N.inline`.
          Defaults to None.
        footer_text (Optional[str], optional): The value for `footer.text`.
          Defaults to None.
        footer_icon_url (Optional[str], optional): The value for `footer.icon_url`.
          Defaults to None.
        timestamp (Optional[Union[str, datetime.datetime]], optional): The value for
          `timestamp`. Defaults to None.

    Returns
    -------
        Message: The message of the embed.
    """

    embed = create_embed(
        author_name=author_name,
        author_url=author_url,
        author_icon_url=author_icon_url,
        title=title,
        url=url,
        thumbnail_url=thumbnail_url,
        description=description,
        image_url=image_url,
        color=color,
        fields=fields,
        footer_text=footer_text,
        footer_icon_url=footer_icon_url,
        timestamp=timestamp,
    )

    return await channel.send(embed=embed, reference=reference)  # type: ignore


async def replace_embed_at(
    message: discord.Message,
    index: int = 0,
    *,
    author_name: Optional[str] = None,
    author_url: Optional[str] = None,
    author_icon_url: Optional[str] = None,
    title: Optional[str] = None,
    url: Optional[str] = None,
    thumbnail_url: Optional[str] = None,
    description: Optional[str] = None,
    image_url: Optional[str] = None,
    color: int = 0,
    fields: Optional[
        Sequence[Union[list[Union[str, bool]], tuple[str, str], tuple[str, str, bool]]]
    ] = None,
    footer_text: Optional[str] = None,
    footer_icon_url: Optional[str] = None,
    timestamp: Optional[Union[str, datetime.datetime]] = None,
) -> discord.Message:
    """Create an embed using the specified arguments and use it to replace
    another embed of a given message at the specified index.

    Parameters
    ----------
        message (discord.Message): The target message.
        index (Optional[int], optional): The optional index of the embed to replace. A value of
          `None` means that all existing embeds will be removed and replaced with the
          single embed generated from this function. If the supplied index is out of
          the range for the message's list of embeds, this function will simply return.
          the input message. Negative indices are also supported. Indices must be below
          `10` and above `-11`. Defaults to None.
        author_name (Optional[str], optional): The value for `author.name`.
          Defaults to None.
        author_url (Optional[str], optional): The value for `author.url`.
          Defaults to None.
        author_icon_url (Optional[str], optional): The value for `author.icon_url`.
          Defaults to None.
        title (Optional[str], optional): The value for `title`.
          Defaults to None.
        url (Optional[str], optional): The value for `url`.
          Defaults to None.
        thumbnail_url (Optional[str], optional): The value for `thumbnail_url`.
          Defaults to None.
        description (Optional[str], optional): The value for `description`.
          Defaults to None.
        image_url (Optional[str], optional): The value for `image.url`.
          Defaults to None.
        color (int, optional): The value for `color`.
          Defaults to 0.
        fields (Optional[
                Sequence[Union[list[Union[str, bool]], tuple[str, str, bool]]]]
          , optional):
          The value for `fields`, which must be a sequence of embed fields.
          Those can be an embed field dictionary or a 3-item list/tuple of
          values for `fields.N.name`, `fields.N.value` and `fields.N.inline`.
          Defaults to None.
        footer_text (Optional[str], optional): The value for `footer.text`.
          Defaults to None.
        footer_icon_url (Optional[str], optional): The value for `footer.icon_url`.
          Defaults to None.
        timestamp (Optional[Union[str, datetime.datetime]], optional): The value for
          `timestamp`. Defaults to None.

    Returns
    -------
        Message: The edited message or the input message depending on the given
          arguments.
    """
    embed = create_embed(
        author_name=author_name,
        author_url=author_url,
        author_icon_url=author_icon_url,
        title=title,
        url=url,
        thumbnail_url=thumbnail_url,
        description=description,
        image_url=image_url,
        color=color,
        fields=fields,
        footer_text=footer_text,
        footer_icon_url=footer_icon_url,
        timestamp=timestamp,
    )

    if index is None:
        return await message.edit(embed=embed)

    embeds = message.embeds.copy()

    embed_count = len(embeds)

    index = embed_count + index if index < 0 else index

    embeds = message.embeds.copy()

    if 0 <= index < len(embeds):
        embeds[index] = embed
        return await message.edit(embeds=embeds)

    return message


async def edit_embed_at(
    message: discord.Message,
    index: int = 0,
    edit_inner_fields: bool = False,
    *,
    author_name: Optional[str] = None,
    author_url: Optional[str] = None,
    author_icon_url: Optional[str] = None,
    title: Optional[str] = None,
    url: Optional[str] = None,
    thumbnail_url: Optional[str] = None,
    description: Optional[str] = None,
    image_url: Optional[str] = None,
    color: int = -1,
    fields: Optional[
        Sequence[Union[list[Union[str, bool]], tuple[str, str], tuple[str, str, bool]]]
    ] = None,
    footer_text: Optional[str] = None,
    footer_icon_url: Optional[str] = None,
    timestamp: Optional[Union[str, datetime.datetime]] = None,
) -> discord.Message:

    """Edit an embed of the given message at the specified index using the specified
    arguments.

    Parameters
    ----------
        message (discord.Embed): The message of the target embed.
        index (int, optional): The optional index of the embed to replace. If the
          supplied index is out of the range for the message's list of embeds,
          this function will simply return the input message. Negative indices
          are also supported. Indices must be below `10` and above `-11`.
          Defaults to 0.
        edit_inner_fields (bool, optional): Whether to use the given embed
          fields to edit existing embed fields present in the target embed,
          by only changing what was supplied. If set to `True` and there are
          more input embed fields than in the target embed, those will be added
          as new embed fields. Note that the structure of those fields must be
          correct to avoid errors.
        author_name (Optional[str], optional): The value for `author.name`.
          Defaults to None.
        author_url (Optional[str], optional): The value for `author.url`.
          Defaults to None.
        author_icon_url (Optional[str], optional): The value for `author.icon_url`.
          Defaults to None.
        title (Optional[str], optional): The value for `title`.
          Defaults to None.
        url (Optional[str], optional): The value for `url`.
          Defaults to None.
        thumbnail_url (Optional[str], optional): The value for `thumbnail_url`.
          Defaults to None.
        description (Optional[str], optional): The value for `description`.
          Defaults to None.
        image_url (Optional[str], optional): The value for `image.url`.
          Defaults to None.
        color (int, optional): The value for `color`.
          Defaults to 0.
        fields (Optional[
                Sequence[Union[list[Union[str, bool]], tuple[str, str, bool]]]]
          , optional):
          The value for `fields`, which must be a sequence of embed fields.
          Those can be an embed field dictionary or a 3-item list/tuple of
          values for `fields.N.name`, `fields.N.value` and `fields.N.inline`.
          Defaults to None.
        footer_text (Optional[str], optional): The value for `footer.text`.
          Defaults to None.
        footer_icon_url (Optional[str], optional): The value for `footer.icon_url`.
          Defaults to None.
        timestamp (Optional[Union[str, datetime.datetime]], optional): The value for
          `timestamp`. Defaults to None.

    Returns
    -------
        discord.Message: A new message with edits applied or the input message.

    Raises
    ------
        ValueError
            Invalid argument structure.
        TypeError
            Invalid argument type.
    """

    embeds = message.embeds.copy()
    embed = None

    if 0 <= index < len(embeds):
        embed = embeds[index]
    else:
        return message

    embeds[index] = edit_embed(  # type: ignore
        embed,
        in_place=False,
        edit_inner_fields=edit_inner_fields,
        author_name=author_name,
        author_url=author_url,
        author_icon_url=author_icon_url,
        title=title,
        url=url,
        thumbnail_url=thumbnail_url,
        description=description,
        image_url=image_url,
        color=color,
        fields=fields,
        footer_text=footer_text,
        footer_icon_url=footer_icon_url,
        timestamp=timestamp,
    )

    return await message.edit(embeds=embeds)


def create_embed_from_dict(embed_dict: dict[str, Any]) -> discord.Embed:
    """Create an embed from a given embed dictionary.

    Parameters
    ----------
        data (dict): The embed dictionary.

    Returns
    -------
        discord.Embed: The new embed.
    """
    embed_dict = copy_embed_dict(embed_dict)
    handle_embed_dict_timestamp(embed_dict)

    return discord.Embed.from_dict(embed_dict)


async def send_embeds_from_dicts(channel: discord.abc.Messageable, *embed_dicts: dict):
    """Sends an embed from a dictionary with a much more tight function"""
    return await channel.send(
        embeds=[create_embed_from_dict(embed_dict) for embed_dict in embed_dicts]
    )


async def replace_embed_from_dict_at(
    message: discord.Message,
    embed_dict: dict[str, Any],
    index: Optional[int] = None,
):
    """Create an embed using the specified embed dictionary and use it to replace
    another embed of a given message at the specified index.

    Parameters
    ----------
        message (discord.Message): The target message.
        index (Optional[int], optional): The optional index of the embed to replace. A value of
          `None` means that all existing embeds will be removed and replaced with the
          single embed generated from this function. If the supplied index is out of
          the range for the message's list of embeds, this function will simply return.
          the input message. Negative indices are also supported. Indices must be below
          `10` and above `-11`. Defaults to None.
        embed_dict (dict): The embed dictionary used for replacement.

    Returns
    -------
        discord.Message: The edited message or the input message depending on the given
          arguments.
    """

    embed_dict = copy_embed_dict(embed_dict)
    handle_embed_dict_timestamp(embed_dict)

    embeds = message.embeds.copy()

    embed_count = len(embeds)

    if index is not None:
        index = embed_count + index if index < 0 else index

        if 0 <= index < len(message.embeds):
            embeds[index] = create_embed_from_dict(embed_dict)
            return await message.edit(embeds=embeds)

        return message

    return await message.edit(embed=create_embed_from_dict(embed_dict))


async def edit_embed_from_dict_at(
    message: discord.Message,
    embed_dict: dict[str, Any],
    index: int = 0,
    add_attributes: bool = True,
    edit_inner_fields: bool = False,
):
    """Edit an embed of a given message at the specified index using the given embed
    dictionary.

    Parameters
    ----------
        message (discord.Message): The target message.
        index (int, optional): The index of the embed to edit.
          If the supplied index is out of the range for the message's list of embeds,
          this function will simply return the input message. Negative indices are
          also supported. Defaults to 0.
        embed_dict (dict): The embed dictionary used for editing.

    Returns
    -------
        discord.Message: The edited message or the input message depending on the given
          arguments.
    """

    embed_dict = copy_embed_dict(embed_dict)
    handle_embed_dict_timestamp(embed_dict)

    embeds = message.embeds.copy()

    embed_count = len(embeds)

    index = embed_count + index if index < 0 else index

    if 0 <= index < len(message.embeds):
        embeds[index] = discord.Embed.from_dict(
            edit_embed_dict_from_dict(
                embeds[index].to_dict(),  # type: ignore
                embed_dict,
                in_place=False,
                add_attributes=add_attributes,
                edit_inner_fields=edit_inner_fields,
            )
        )
        return await message.edit(embeds=embeds)

    return message


def edit_embed_from_dict(
    embed: discord.Embed,
    update_embed_dict: dict[str, Any],
    in_place: bool = True,
    add_attributes: bool = True,
    edit_inner_fields: bool = False,
) -> Optional[discord.Embed]:
    """Edit the attributes of a given embed using another dictionary.

    Parameters
    ----------
        embed (discord.Embed): The target embed.
        update_embed_dict (dict): The embed dictionary used for modification.
        in_place (bool, optional): Whether to do this operation on the given embed
          "in place" and to return `None` instead of a new embed. Defaults to True.
        add_attributes (bool, optional): Whether the embed attributes in
          'update_embed_dict' should be added to the new modified embed if not
          present in the target. Defaults to True.
        edit_inner_fields (bool, optional): Whether to modify the 'fields' attribute
          of an embed as one unit or to modify the embeds fields themselves, one by
          one. Defaults to False.
    """
    if in_place:
        if update_embed_dict.get("title") is not None:
            embed.title = update_embed_dict["title"]

        if update_embed_dict.get("url") is not None:
            embed.url = update_embed_dict["url"]

        if update_embed_dict.get("description") is not None:
            embed.description = update_embed_dict["description"]

        if 0 <= update_embed_dict.get("color", -1) <= 0xFFFFFF:
            embed.color = update_embed_dict["color"]

        if update_embed_dict.get("timestamp") is not None:
            timestamp = update_embed_dict["timestamp"]
            if isinstance(timestamp, str):
                try:
                    embed.timestamp = datetime.datetime.fromisoformat(
                        timestamp.removesuffix("Z")
                    )
                except ValueError:
                    pass
            elif isinstance(timestamp, datetime.datetime):
                embed.timestamp = timestamp
            else:
                raise TypeError(
                    "key 'timestamp' of argument 'update_embed_dict' must have None "
                    "or a string or datetime object as a value"
                )

        if update_embed_dict.get("author") is not None:
            auth = update_embed_dict["author"]
            if not isinstance(auth, dict):
                raise TypeError(
                    "key 'author' of argument 'update_embed_dict' must have None "
                    "or a dictionary with the structure "
                    "`{'name': '...', ['url': '...', 'icon_url': '...']}` "
                    "as a value"
                )
            auth_name = auth.get("name")
            auth_url = auth["url"] if auth.get("url") is not None else embed.author.url
            auth_icon_url = (
                auth["icon_url"]
                if auth.get("icon_url") is not None
                else embed.author.icon_url
            )

            if auth_name is not None:
                embed.set_author(name=auth_name, url=auth_url, icon_url=auth_icon_url)

        if update_embed_dict.get("footer") is not None:
            footer = update_embed_dict["footer"]
            if not isinstance(footer, dict):
                raise TypeError(
                    "key 'footer' of argument 'update_embed_dict' must have None "
                    "or a dictionary with the structure "
                    "`{'text': '...'[, 'icon_url': '...']}` "
                    "as a value"
                )
            footer_text = footer.get("text")
            footer_icon_url = (
                footer["icon_url"]
                if footer.get("icon_url") is not None
                else embed.author.icon_url
            )

            if footer_text is not None:
                embed.set_footer(text=footer_text, icon_url=footer_icon_url)

        if update_embed_dict.get("thumbnail") is not None:
            thumbnail = update_embed_dict["thumbnail"]
            if not isinstance(thumbnail, dict):
                raise TypeError(
                    "key 'thumbnail' of argument 'update_embed_dict' must have None "
                    "or a dictionary with the structure `{'url': '...'}` "
                    "as a value"
                )
            thumbnail_url = thumbnail.get("url")
            if thumbnail_url is not None:
                embed.set_thumbnail(url=thumbnail_url)

        if update_embed_dict.get("image") is not None:
            image = update_embed_dict["image"]
            if not isinstance(image, dict):
                raise TypeError(
                    "key 'image' of argument 'update_embed_dict' must have None "
                    "or a dictionary with the structure `{'url': '...'}` "
                    "as a value"
                )
            image_url = image.get("url")
            if image_url is not None:
                embed.set_image(url=image_url)

        embed_fields = embed.fields
        embed_field_count = len(embed_fields)

        if update_embed_dict.get("fields") is not None:
            for i, field in enumerate(update_embed_dict["fields"]):
                if i < embed_field_count and edit_inner_fields:
                    embed_field = embed_fields[i]

                    name = embed_field.name
                    value = embed_field.value
                    inline = embed_field.inline

                    if isinstance(field, dict):
                        name, value, inline = (
                            field.get("name", name),
                            field.get("value", value),
                            field.get("inline", inline),
                        )
                    else:
                        raise TypeError(
                            f" invalid embed field type at `fields[{i}]`: an embed "
                            "field must be a dictionary of the structure "
                            "`{'name': '...', 'value': '...'[, 'inline': True/False]}`"
                            " or a dictionary with the keys "
                            "'name', 'value', inline' containing values of those "
                            "same types "
                        )

                    if (
                        not isinstance(name, str)
                        or not isinstance(value, str)
                        or not isinstance(inline, bool)
                    ):
                        raise ValueError(
                            f" invalid embed field at `fields[{i}]`: an embed "
                            "field must be a dictionary of the structure "
                            "`{'name': '...', 'value': '...'[, 'inline': True/False]}`"
                            " or a dictionary with the keys "
                            "'name', 'value', inline' containing values of those "
                            "same types "
                        )

                    embed.set_field_at(
                        i,
                        name=name,
                        value=value,
                        inline=inline or False,
                    )

                else:
                    name = value = inline = None
                    if isinstance(field, dict):
                        name, value, inline = (
                            field.get("name"),
                            field.get("value"),
                            field.get("inline", True),
                        )
                    elif isinstance(field, (list, tuple)):
                        name, value, *overflow = field
                        if overflow:
                            inline = overflow[0]

                    else:
                        raise TypeError(
                            f" invalid embed field type at `fields[{i}]`: an embed "
                            "field must be a dictionary of the structure "
                            "`{'name': '...', 'value': '...'[, 'inline': True/False]}`"
                            " or a dictionary with the keys "
                            "'name', 'value', inline' containing values of those "
                            "same types "
                        )

                    if (
                        not isinstance(name, str)
                        or not isinstance(value, str)
                        or not isinstance(inline, bool)
                    ):
                        raise ValueError(
                            f" invalid embed field at `fields[{i}]`: an embed "
                            "field must be a dictionary of the structure "
                            "`{'name': '...', 'value': '...'[, 'inline': True/False]}`"
                            " or a dictionary with the keys "
                            "'name', 'value', inline' containing values of those "
                            "same types "
                        )

                    embed.add_field(
                        name=name,
                        value=value,
                        inline=inline or False,
                    )

        return

    return discord.Embed.from_dict(
        edit_embed_dict_from_dict(
            embed.to_dict(),  # type: ignore
            update_embed_dict,
            in_place=False,
            add_attributes=add_attributes,
            edit_inner_fields=edit_inner_fields,
        )
    )


def edit_embed_dict_from_dict(
    old_embed_dict: dict[str, Any],
    update_embed_dict: dict[str, Any],
    in_place: bool = True,
    add_attributes: bool = True,
    edit_inner_fields: bool = False,
) -> Optional[dict[str, Any]]:
    """Edit the attributes of a given embed dictionary using another dictionary.

    Parameters
    ----------
        old_embed_dict (dict): The target embed dictionary.
        update_embed_dict (dict): The embed dictionary used for modification.
        in_place (bool, optional): Whether to do this operation on the given embed
          "in place" and to return `None` instead of a new embed. Defaults to True.
        add_attributes (bool, optional): Whether the embed attributes in
          'update_embed_dict' should be added to the new modified embed if not
          present in the target. Defaults to True.
        edit_inner_fields (bool, optional): Whether to modify the 'fields' attribute
          of an embed as one unit or to modify the embeds fields themselves, one by
          one. Defaults to False.

    Returns
    -------
        Optional[dict[str, Any]]: A new embed dictionary or `None` depending on the given
          arguments.
    """

    if not in_place:
        old_embed_dict = copy_embed_dict(old_embed_dict)

    handle_embed_dict_timestamp(old_embed_dict)

    if edit_inner_fields:
        if "fields" in old_embed_dict:
            old_embed_dict["fields"] = {
                str(i): old_embed_dict["fields"][i]
                for i in range(len(old_embed_dict["fields"]))
            }
        if "fields" in update_embed_dict:
            update_embed_dict["fields"] = {
                str(i): update_embed_dict["fields"][i]
                for i in range(len(update_embed_dict["fields"]))
            }

    recursive_mapping_update(
        old_embed_dict, update_embed_dict, add_new_keys=add_attributes
    )

    if edit_inner_fields:
        if "fields" in old_embed_dict:
            old_embed_dict["fields"] = [
                old_embed_dict["fields"][i]
                for i in sorted(old_embed_dict["fields"].keys())
            ]
        if "fields" in update_embed_dict:
            update_embed_dict["fields"] = [
                update_embed_dict["fields"][i]
                for i in sorted(update_embed_dict["fields"].keys())
            ]

    if not in_place:
        return old_embed_dict

    return None


def _read_embed_field_dict(
    field_dict: Sequence[
        Union[list[Union[str, bool]], tuple[str, str], tuple[str, str, bool]]
    ],
    allow_incomplete: bool = False,
    index: Optional[int] = None,
) -> tuple[Optional[str], Optional[str], Optional[bool]]:
    err_str = f" at `fields[{index}]`" if index is not None else ""
    name = value = inline = None

    if isinstance(field_dict, dict):
        name, value, inline = (
            field_dict.get("name"),
            field_dict.get("value"),
            field_dict.get("inline"),
        )
    else:
        raise TypeError(
            f"invalid embed field type{err_str}: an embed "
            "field must be a dictionary of the structure "
            "`{'name': '...', 'value': '...'[, 'inline': True/False]}`"
        )

    if (
        not any((name, value, inline))
        or (
            not isinstance(name, str)
            or not isinstance(value, str)
            or not isinstance(inline, bool)
        )
        and not allow_incomplete
    ):
        raise ValueError(
            f"invalid embed field{err_str}: an embed "
            "field must be a dictionary of the structure "
            "`{'name': '...', 'value': '...'[, 'inline': True/False]}`"
        )

    return name, value, inline


def add_embed_fields_from_dicts(
    embed: discord.Embed,
    *field_dicts: dict,
    in_place=True,
) -> Optional[discord.Embed]:
    """Add embed fields to an embed from the given embed field dictionaries.

    Parameters
    ----------
        embed (discord.Embed): The target embed.
        in_place (bool, optional): Whether to do this operation on the given embed
          "in place" and to return `None` instead of a new embed. Defaults to True.

    Returns
    -------
        Optional[discord.Embed]: A new embed or `None` depending on the given
          arguments.

    Raises
    ------
        TypeError
            Invalid argument types.
        ValueError
            Invalid argument structure.
    """

    if not in_place:
        embed = embed.copy()

    for i, field in enumerate(field_dicts):
        name = value = inline = None
        if isinstance(field, dict):
            name, value, inline = (
                field.get("name"),
                field.get("value"),
                field.get("inline", True),
            )
        else:
            raise TypeError(
                f" invalid embed field type at `fields[{i}]`: an embed "
                "field must be a dictionary of the structure "
                "`{'name': '...', 'value': '...'[, 'inline': True/False]}`"
            )

        if (
            not isinstance(name, str)
            or not isinstance(value, str)
            or not isinstance(inline, bool)
        ):
            raise ValueError(
                f" invalid embed field at `fields[{i}]`: an embed "
                "field must be a dictionary of the structure "
                "`{'name': '...', 'value': '...'[, 'inline': True/False]}`"
            )

        embed.add_field(
            name=name,
            value=value,
            inline=inline or False,
        )

    if not in_place:
        return embed

    return


def insert_embed_fields_from_dicts(
    embed: discord.Embed, index: int, *field_dicts: dict, in_place: bool = True
) -> Optional[discord.Embed]:
    """Insert embed fields to an embed at a specified index from the given
    embed field dictionaries.

    Parameters
    ----------
        embed (discord.Embed): The target embed.
        index (int): The index to insert the fields at.
        *field_dicts (dict): The embed field dictionaries.
        in_place (bool, optional): Whether to do this operation on the given embed
          "in place" and to return `None` instead of a new embed. Defaults to True.

    Returns
    -------
        Optional[discord.Embed]: A new embed or `None` depending on the given
          arguments.
    """
    fields_count = len(embed.fields)
    index = fields_count + index if index < 0 else index

    if not in_place:
        embed = embed.copy()

    for i, field in enumerate(field_dicts):
        name, value, inline = _read_embed_field_dict(field_dict=field, index=i)  # type: ignore
        embed.insert_field_at(
            index,
            name=name,
            value=value,
            inline=inline or False,
        )

    if not in_place:
        return embed

    return


def edit_embed_field_from_dict(
    embed: discord.Embed, index: int, field_dict: dict, in_place: bool = True
) -> Optional[discord.Embed]:
    """Edits parts of an embed field of the embed of a message from a
    dictionary
    """

    if not in_place:
        embed = embed.copy()

    fields_count = len(embed.fields)
    index = fields_count + index if index < 0 else index

    embed_dict = embed.to_dict()

    if "fields" in embed_dict:
        if 0 <= index < fields_count:
            old_field_dict = embed_dict["fields"][index].copy()

            for k in field_dict:
                if k in old_field_dict and field_dict[k] is not None:
                    old_field_dict[k] = field_dict[k]

            embed.set_field_at(
                index,
                name=old_field_dict["name"],
                value=old_field_dict["value"],
                inline=old_field_dict.get("inline", False),
            )

    if not in_place:
        return embed

    return


def edit_embed_fields_from_dicts(
    embed: discord.Embed, *field_dicts: dict, in_place: bool = True
) -> Optional[discord.Embed]:
    """Edits embed fields in the embed of a message from dictionaries"""

    if not in_place:
        embed = embed.copy()

    embed_dict = embed.to_dict()
    old_field_dicts = embed_dict.get("fields", [])
    old_field_dicts_len = len(old_field_dicts)
    field_dicts_len = len(field_dicts)

    for i in range(old_field_dicts_len):
        if i > field_dicts_len - 1:
            break

        old_field_dict = old_field_dicts[i]
        field_dict = field_dicts[i]

        if field_dict:
            for k in field_dict:
                if k in old_field_dict and field_dict[k] != None:
                    old_field_dict[k] = field_dict[k]

            embed.set_field_at(
                i,
                name=old_field_dict["name"],
                value=old_field_dict["value"],
                inline=old_field_dict.get("inline", False),
            )

    if not in_place:
        return embed

    return


async def remove_embed_fields(
    embed: discord.Embed, *field_indices: int, in_place: bool = True
) -> Optional[discord.Embed]:
    """Removes multiple embed fields of the embed of a message from a
    dictionary
    """

    if not in_place:
        embed = embed.copy()

    fields_count = len(embed.fields)

    parsed_field_indices = [
        fields_count + idx if idx < 0 else idx for idx in field_indices
    ]

    parsed_field_indices.sort(reverse=True)

    for index in parsed_field_indices:
        embed.remove_field(index)

    if not in_place:
        return embed

    return


def swap_embed_fields(
    embed: discord.Embed, index_a: int, index_b: int, in_place: bool = True
) -> Optional[discord.Embed]:
    """Swaps two embed fields of the embed of a message from a
    dictionary
    """

    if not in_place:
        embed = embed.copy()

    fields_count = len(embed.fields)
    index_a = fields_count + index_a if index_a < 0 else index_a
    index_b = fields_count + index_b if index_b < 0 else index_b

    embed_dict = embed.to_dict()

    if "fields" in embed_dict:
        fields_list = embed_dict["fields"]
        fields_list[index_a], fields_list[index_b] = (
            fields_list[index_b],
            fields_list[index_a],
        )

    if not in_place:
        return embed

    return


async def clone_embed_field(embed: discord.Embed, index: int, in_place: bool = True):
    """Duplicates an embed field"""

    if not in_place:
        embed = embed.copy()

    fields_count = len(embed.fields)
    index = fields_count + index if index < 0 else index

    if 0 <= index < fields_count:
        cloned_field = embed.fields[index]
        embed.insert_field_at(
            index,
            name=cloned_field.name,
            value=cloned_field.value,
            inline=cloned_field.inline,
        )

    if not in_place:
        return embed

    return


async def clone_embed_fields(
    embed: discord.Embed,
    *field_indices: int,
    insertion_index: Optional[Union[int, Sequence[int]]] = None,
    in_place: bool = True,
):
    """Duplicates multiple embed fields of the embed of a message
    from a dictionary
    """

    if not in_place:
        embed = embed.copy()

    fields_count = len(embed.fields)

    parsed_field_indices = [
        fields_count + idx if idx < 0 else idx for idx in field_indices
    ]

    parsed_field_indices.sort(reverse=True)

    insertion_indices = ()

    if isinstance(insertion_index, (int, Sequence)):
        if isinstance(insertion_index, int):
            insertion_index = (
                fields_count + insertion_index
                if insertion_index < 0
                else insertion_index
            )
            insertion_indices = (insertion_index,)
        else:
            insertion_indices = insertion_index
            insertion_indices = tuple(
                fields_count + insertion_index
                if insertion_index < 0
                else insertion_index
                for insertion_index in insertion_indices
            )

        cloned_fields = tuple(
            embed.fields[index] for index in sorted(field_indices, reverse=True)
        )
        for cloned_field in cloned_fields:
            for insertion_index in insertion_indices:
                embed.insert_field_at(
                    insertion_index,
                    name=cloned_field.name,
                    value=cloned_field.value,
                    inline=cloned_field.inline,
                )
    else:
        cloned_fields = tuple(
            embed.fields[index] for index in sorted(field_indices, reverse=True)
        )
        for cloned_field in cloned_fields:
            embed.add_field(
                name=cloned_field.name,
                value=cloned_field.value,
                inline=cloned_field.inline,
            )

    if not in_place:
        return embed

    return


def import_embed_data(
    source: Union[str, io.StringIO],
    input_format: Literal[
        "STRING", "JSON", "JSON_STRING", "STRING_BUFFER", "FILE_PATH"
    ] = "JSON_STRING",
    output_format: Literal["STRING", "DICTIONARY"] = "DICTIONARY",
):
    """Import embed data from a file or a string containing JSON
    or a Python dictionary and return it as a Python dictionary or string.
    """

    if input_format.upper() in ("JSON", "JSON_STRING"):
        if input_format.upper() == "JSON_STRING":
            if not isinstance(source, str):
                raise TypeError(
                    f"invalid source for format '{source}': Must be a str object"
                )
            json_data = json.loads(source)

            if (
                not isinstance(json_data, dict)
                and output_format.upper() == "DICTIONARY"
            ):
                raise TypeError(
                    "The given string must contain a JSON object that"
                    " can be converted into a Python `dict` object"
                )
            if output_format.upper() == "STRING":
                json_data = json.dumps(json_data)

            return json_data

        else:
            if not isinstance(source, io.StringIO):
                raise TypeError(
                    f"invalid source for format '{source}': Must be an io.StringIO object"
                )
            json_data = json.load(source)

            if (
                not isinstance(json_data, dict)
                and output_format.upper() == "DICTIONARY"
            ):
                raise TypeError(
                    f"the file at '{source}' must contain a JSON object that"
                    " can be converted into a Python `dict` object"
                )
            if output_format.upper() == "STRING":
                json_data = json.dumps(json_data)

            return json_data

    elif input_format.upper() == "STRING":
        if not isinstance(source, str):
            raise TypeError(
                f"invalid source for format '{source}': Must be a str object"
            )
        try:
            data = literal_eval(source)
        except Exception as e:
            raise TypeError(
                "The contents of the given object for 'source' must be parsable into "
                "literal Python strings, bytes, numbers, tuples, lists, dicts, sets, "
                "booleans, and None."
            ) from e

        if not isinstance(data, dict) and output_format.upper() == "DICTIONARY":
            raise TypeError(
                f"the argument for '{source}' must be of type dict"
                f", not "
                f"'{type(data).__name__}'"
            )

        if output_format.upper() == "STRING":
            return repr(data)

        return data

    else:
        data = None
        if input_format == "STRING_BUFFER":
            if not isinstance(source, io.StringIO):
                raise TypeError(
                    f"invalid source for format '{source}': Must be an io.StringIO object"
                )

            if output_format.upper() == "STRING":
                data = source.getvalue()
            else:
                try:
                    data = literal_eval(source.getvalue())
                except Exception as e:
                    raise TypeError(
                        f", not '{type(data)}'"
                        f"the content of the file at '{source}' must be parsable into a"
                        "literal Python strings, bytes, numbers, tuples, lists, dicts, sets, booleans, and None."
                    ) from e

                if not isinstance(data, dict) and output_format.upper() == "DICTIONARY":
                    raise TypeError(
                        f"the file at '{source}' must be of type dict"
                        f", not '{type(data)}'"
                    )
        elif input_format == "FILE_PATH":
            if not isinstance(source, str):
                raise TypeError(
                    f"invalid source for format '{source}': Must be a str object"
                )

            with open(source, "r", encoding="utf-8") as d:
                if output_format.upper() == "STRING":
                    data = d.read()
                else:
                    try:
                        data = literal_eval(d.read())
                    except Exception as e:
                        raise TypeError(
                            f", not '{type(data)}'"
                            f"the content of the file at '{source}' must be parsable into a"
                            "literal Python strings, bytes, numbers, tuples, lists, dicts, sets, booleans, and None."
                        ) from e

                    if (
                        not isinstance(data, dict)
                        and output_format.upper() == "DICTIONARY"
                    ):
                        raise TypeError(
                            f"the file at '{source}' must be of type dict"
                            f", not '{type(data)}'"
                        )
        else:
            err_str = "invalid input format string"
            raise ValueError(err_str) if isinstance(input_format, str) else TypeError(
                err_str
            )

        return data


def export_embed_data(
    data: Union[dict, tuple, list],
    fp: Optional[Union[str, io.StringIO]] = None,
    indent: Optional[int] = None,
    as_json: bool = True,
    always_return: bool = False,
) -> Optional[str]:
    """Export embed data to serialized JSON or a Python dictionary and store it in a file or a string."""

    if as_json:
        return_data = None
        if isinstance(fp, str):
            with open(fp, "w", encoding="utf-8") as fobj:
                json.dump(data, fobj, indent=indent)
            if always_return:
                return_data = json.dumps(data, indent=indent)

        elif isinstance(fp, io.StringIO):
            json.dump(data, fp, indent=indent)
            if always_return:
                return_data = fp.getvalue()
        else:
            return_data = json.dumps(data, indent=indent)

        return return_data

    else:
        return_data = None
        if isinstance(fp, str):
            with open(fp, "w", encoding="utf-8") as fobj:
                if always_return:
                    return_data = black.format_str(
                        repr(data),
                        mode=black.FileMode(),
                    )
                    fobj.write(return_data)
                else:
                    fobj.write(
                        black.format_str(
                            repr(data),
                            mode=black.FileMode(),
                        )
                    )

        elif isinstance(fp, io.StringIO):
            if always_return:
                return_data = black.format_str(
                    repr(data),
                    mode=black.FileMode(),
                )
                fp.write(return_data)
                fp.seek(0)
            else:
                fp.write(
                    black.format_str(
                        repr(data),
                        mode=black.FileMode(),
                    )
                )
                fp.seek(0)
        else:
            return_data = repr(data)

        return return_data
