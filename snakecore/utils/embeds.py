"""This file is a part of the source code for snakecore.
This project has been licensed under the MIT license.
Copyright (c) 2022-present pygame-community

This file defines some utility functions for working with discord.py's Embed objects.
"""

import datetime
import re
from typing import (
    Any,
    Mapping,
    Optional,
    Sequence,
    TypedDict,
    Union,
    overload,
)

import discord
import discord.types.embed
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
    embed_dict : Mapping[str, Any]
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
    exceptions for structural errors. Note that the output embed dictionary of this
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
