"""This file is a part of the source code for snakecore.
This project has been licensed under the MIT license.
Copyright (c) 2022-present pygame-community

This file defines some important embed related utility functions.
"""

import datetime
import io
import json
import re
from ast import literal_eval
from typing import Literal, Optional, Sequence, TypedDict, Union

import black
import discord

from .utils import recursive_mapping_update


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

EMBED_SYSTEM_ATTRIBUTES_SET = {
    "provider",
    "proxy_url",
    "proxy_icon_url",
    "width",
    "height",
    "type",
}

EMBED_NON_SYSTEM_ATTRIBUTES_SET = {
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

EMBED_CHARACTER_LIMIT = 6000

EMBED_FIELD_LIMIT = 25

EMBED_ATTRIBUTE_CHARACTER_LIMIT_DICT = {
    "author": {
        "name": 256,
    },
    "title": 256,
    "description": 4096,
    "fields": [{"name": 256, "value": 1024}],
    "footer": {
        "text": 2048,
    },
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

EmbedDict = dict[
    str,
    Union[
        str, int, dict[str, str], list[dict[str, Union[str, bool]]], datetime.datetime
    ],
]


def create_embed_mask_dict(
    attributes: str = "",
    allow_system_attributes: bool = False,
    fields_as_field_dict: bool = False,
) -> EMBED_MASK_DICT_HINT:
    """Create an embed mask dictionary based on the attributes specified in the given
    string. This is mostly used for internal purposes relating to comparing and
    modifying embed dictionaries. All embed attributes are set to `None` by default,
    which will be ignored by `discord.Embed`.

    Args:
        attributes (str, optional): The attribute string. Defaults to "", which will
        returned all valid attributes of an embed.
        allow_system_attributes (bool, optional): Whether to include embed attributes
        that can not be manually set by bot users. Defaults to False.
        fields_as_field_dict (bool, optional): Whether the embed `fields` attribute
          returned in the output dictionary of this function should be a dictionary
          that maps stringized indices to embed field dictionaries. Defaults to False.

    Raises:
        ValueError: Invalid embed attribute string.

    Returns:
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

    all_system_attribs_set = EMBED_SYSTEM_ATTRIBUTES_SET

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
                        if (
                            attr[i - 1] == "fields"
                            and "(" not in attr[i]
                            and ")" not in attr[i]
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
                    if attr[i].startswith("(") and attr[i].endswith(")"):
                        if not attr[i].startswith("(") and not attr[i].endswith(")"):
                            raise ValueError(
                                "Invalid embed attribute filter string! "
                                "Embed field ranges should only contain integers "
                                "and should be structured like this: "
                                "`fields.(start, stop[, step]).attribute`"
                            )
                        field_str_range_list = [v for v in attr[i][1:][:-1].split(",")]
                        field_range_list = []

                        for j in range(len(field_str_range_list)):
                            if (
                                field_str_range_list[j].isnumeric()
                                or len(field_str_range_list[j]) > 1
                                and field_str_range_list[j][1:].isnumeric()
                            ):
                                field_range_list.append(int(field_str_range_list[j]))
                            else:
                                raise ValueError(
                                    "Invalid embed attribute filter string! "
                                    "Embed field ranges should only contain integers "
                                    "and should be structured like this: "
                                    "`fields.(start, stop[, step]).attribute`"
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

                        field_range = range(*field_range_list)
                        if not field_range:
                            raise ValueError(
                                "Invalid embed attribute filter string! "
                                "Empty field range!"
                            )
                        for j in range(*field_range_list):
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
                            "`fields.(start,stop[,step]).attribute`. Note that embed "
                            "field ranges cannot contain whitespace."
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


def check_embed_dict_char_count(embed_dict: EmbedDict) -> int:
    """Count the number of characters in the text fields of an embed dictionary.

    Args:
        embed_dict (EmbedDict): The target embed dictionary.

    Returns:
        int: The character count.
    """
    count = 0

    author = embed_dict.get("author")
    if author is not None:
        count += len(author.get("name", ""))

    count += len(embed_dict.get("title", "")) + len(embed_dict.get("description", ""))

    fields = embed_dict.get("fields", ())

    for field in fields:
        count += len(field.get("name", "")) + len(field.get("value", ""))

    footer = embed_dict.get("footer")
    if footer is not None:
        count += len(footer.get("text", ""))

    return count


def validate_embed_dict_char_count(embed_dict: EmbedDict) -> bool:
    """Check if all text attributes of an embed dictionary are below their respective
    character limits.

    Args:
        embed_dict (dict): The target embed dictionary.

    Returns:
        bool: The result.
    """

    count = 0

    author = embed_dict.get("author")
    if author is not None:
        author_name_count = len(author.get("name", ""))
        if author_name_count > EMBED_ATTRIBUTE_CHARACTER_LIMIT_DICT["author"]["name"]:
            return False
        count += author_name_count

    title_count = len(embed_dict.get("title", ""))
    if title_count > EMBED_ATTRIBUTE_CHARACTER_LIMIT_DICT["title"]:
        return False

    count += title_count

    description_count = len(embed_dict.get("description", ""))
    if description_count > EMBED_ATTRIBUTE_CHARACTER_LIMIT_DICT["description"]:
        return False

    count += description_count

    fields = embed_dict.get("fields", [])

    if len(fields) > EMBED_FIELD_LIMIT:
        return False

    for field in fields:
        field_name_count = len(field.get("name", ""))
        field_value_count = len(field.get("value", ""))

        if (
            field_name_count > EMBED_ATTRIBUTE_CHARACTER_LIMIT_DICT["fields"][0]["name"]
            or field_value_count
            > EMBED_ATTRIBUTE_CHARACTER_LIMIT_DICT["fields"][0]["value"]
        ):
            return False

        count += field_name_count + field_value_count

    footer = embed_dict.get("footer")
    if footer is not None:
        footer_text_count = len(footer.get("text", ""))

        if footer_text_count > EMBED_ATTRIBUTE_CHARACTER_LIMIT_DICT["footer"]["text"]:
            return False

        count += footer_text_count

    return count <= EMBED_CHARACTER_LIMIT


def validate_embed_dict(embed_dict: EmbedDict) -> bool:
    """Checks if an embed dictionary can produce
    a viable embed on Discord. This also includes keeping to character limits on all
    embed attributes.

    Args:
        embed_dict (dict): The target embed dictionary

    Returns:
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
            and ("url" not in v or not isinstance(v["url"], str) or not v["url"])
            or k == "author"
            and (
                "name" not in v
                or any(
                    ak in v and (not isinstance(v[ak], str) or not v[ak])
                    for ak in ("name", "url", "icon_url")
                )
            )
            or k == "footer"
            and (
                "text" not in v
                or any(
                    ak in v and (not isinstance(v[ak], str) or not v[ak])
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


def filter_embed_dict(
    embed_dict: EmbedDict, in_place: bool = True
) -> Optional[EmbedDict]:
    """Delete invalid embed attributes in the given embed dictionary that would cause
    exceptionsfor structural errors. Note that the output embed dictionary of this
    function might still not be a viable embed dictionary to be sent to Discord's
    servers.

    Args:
        embed_dict (dict): The target embed dictionary.
        in_place (bool, optional): Whether to do this operation on the given embed
          dictionary "in place" and to return `None` instead of a new dictionary.
          Defaults to True.

    Returns:
        Optional[dict]: A new filtered embed dictionary or `None` depending on the
          given arguments.
    """

    if not in_place:
        embed_dict = copy_embed_dict(embed_dict)

    if not embed_dict or not isinstance(embed_dict, dict):
        return False

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
                    ak in v and (not isinstance(v[ak], str) or not v[ak])
                    for ak in ("name", "url", "icon_url")
                )
            )
            or k == "footer"
            and (
                "text" not in v
                or any(
                    ak in v and (not isinstance(v[ak], str) or not v[ak])
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

            for i, f in reversed(tuple(enumerate(v))):
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
                    v.pop(i)

        elif k == "timestamp":
            if not isinstance(v, str):
                return False
            try:
                datetime.datetime.fromisoformat(embed_dict[k])
            except ValueError:
                del embed_dict[k]

    if not in_place:
        return embed_dict

    return


def handle_embed_dict_timestamp(
    embed_dict: EmbedDict, *, in_place: bool = True
) -> Optional[EmbedDict]:
    """Correct or delete the `"timestamp"` key's value in an embed dictionary.

    Args:
        embed_dict (dict): The embed dictionary.
        in_place (bool, optional): Whether to do this operation on the given embed
          dictionary "in place" and to return `None` instead of a new dictionary.
          Defaults to True.

    Returns:
        Optional[dict]: A new embed dictionary, depending on which arguments were
          given.
    """

    if not in_place:
        embed_dict = copy_embed_dict(embed_dict)

    if "timestamp" in embed_dict:
        timestamp = embed_dict.get("timestamp")
        if isinstance(embed_dict.get("timestamp"), str):
            try:
                final_timestamp = embed_dict["timestamp"].removesuffix("Z")
                datetime.datetime.fromisoformat(final_timestamp)
                embed_dict["timestamp"] = final_timestamp
            except ValueError:
                del embed_dict["timestamp"]
        elif isinstance(embed_dict.get("timestamp"), datetime.datetime):
            embed_dict["timestamp"] = timestamp.isoformat()
        else:
            del embed_dict["timestamp"]

    if not in_place:
        return embed_dict

    return


def copy_embed_dict(embed_dict: EmbedDict) -> EmbedDict:
    """Make a shallow copy of the given embed dictionary,
    and embed fields (if present).

    Args:
        embed_dict (dict): The target embed dictionary.

    Returns:
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
) -> list[dict[str, Union[str, bool]]]:
    """Extract embed field string syntax from the given string(s).
    Syntax of an embed field string: `<name|value[|inline]>`.

    Args:
        *strings (str): The target strings to extract from.
        return_field_lists (bool, optional): _description_. Defaults to True.

    Returns:
        list[dict[str, Union[str, bool]]]: A list of embed
          field dictionaries with keys `"name"`, `"value"` and `"inline"`.
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

                field_data[2] = (
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
    """
    Parses the condensed embed list syntax used in some embed creation
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

    return embed_args


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
    fields: Optional[Sequence[dict[str, Union[str, bool]]]] = None,
    footer_text: Optional[str] = None,
    footer_icon_url: Optional[str] = None,
    timestamp: Optional[Union[str, datetime.datetime]] = None,
) -> EmbedDict:

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
            name, value, inline = _read_embed_field_dict(field_dict=field, index=i)
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
    fields: Optional[Sequence[dict[str, Union[str, bool]]]] = None,
    footer_text: Optional[str] = None,
    footer_icon_url: Optional[str] = None,
    timestamp: Optional[Union[str, datetime.datetime]] = None,
) -> discord.Embed:
    """Create an embed using the specified arguments.

    Args:
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

    Returns:
        Embed: The created embed.

    Raises:
        TypeError: invalid argument types.
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
            name, value, inline = _read_embed_field_dict(field_dict=field, index=i)
            embed.add_field(
                name=name,
                value=value,
                inline=inline,
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
    fields: Optional[Sequence[dict[str, Union[str, bool]]]] = None,
    footer_text: Optional[str] = None,
    footer_icon_url: Optional[str] = None,
    timestamp: Optional[Union[str, datetime.datetime]] = None,
) -> Optional[discord.Embed]:

    """Edit a given embed using the specified arguments.

    Args:
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

    Returns:
        Optional[discord.Embed]: A new embed with edits applied or `None`.

    Raises:
        ValueError: Invalid argument structure.
        TypeError: Invalid argument type.
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
                        field_dict=field, index=i
                    )
                    embed.set_field_at(
                        i,
                        name=name,
                        value=value,
                        inline=inline,
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
                        inline=inline,
                    )

        if footer_text is not None:
            embed.set_footer(text=footer_text, icon_url=footer_icon_url)

    else:
        old_embed_dict = embed.to_dict()
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
                old_embed_dict["fields"] = {
                    str(i): old_embed_dict["fields"][i]
                    for i in range(len(old_embed_dict["fields"]))
                }
            if "fields" in update_embed_dict:
                update_embed_dict["fields"] = {
                    str(i): update_embed_dict["fields"][i]
                    for i in range(len(update_embed_dict["fields"]))
                }

        recursive_mapping_update(old_embed_dict, update_embed_dict, add_new_keys=True)

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

        return discord.Embed.from_dict(old_embed_dict)


async def send_embed(
    channel: discord.abc.Messageable,
    reference: Optional[Union[discord.Message, discord.MessageReference]] = None,
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
    """Create an embed using the given arguments and send it to a
    `discord.abc.Messageable` and return the resulting message.

    Args:
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

    Returns:
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

    return await channel.send(embed=embed, reference=reference)


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

    Args:
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

    Returns:
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

    Args:
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

    Returns:
        discord.Message: A new message with edits applied or the input message.

    Raises:
        ValueError: Invalid argument structure.
        TypeError: Invalid argument type.
    """

    embeds = message.embeds.copy()
    embed = None

    if 0 <= index < len(embeds):
        embed = embeds[index]
    else:
        return message

    embeds[index] = edit_embed(
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


def create_embed_from_dict(embed_dict: EmbedDict) -> discord.Embed:
    """Create an embed from a given embed dictionary.

    Args:
        data (dict): The embed dictionary.

    Returns:
        discord.Embed: The new embed.
    """
    embed_dict = copy_embed_dict(embed_dict)
    handle_embed_dict_timestamp(embed_dict)

    return discord.Embed.from_dict(embed_dict)


async def send_embeds_from_dicts(
    channel: discord.abc.Messageable, *embed_dicts: EmbedDict
):
    """Sends an embed from a dictionary with a much more tight function"""
    return await channel.send(
        embeds=[create_embed_from_dict(embed_dict) for embed_dict in embed_dicts]
    )


async def replace_embed_from_dict_at(
    message: discord.Message, embed_dict: EmbedDict, index: Optional[int] = None
):
    """Create an embed using the specified embed dictionary and use it to replace
    another embed of a given message at the specified index.

    Args:
        message (discord.Message): The target message.
        index (Optional[int], optional): The optional index of the embed to replace. A value of
          `None` means that all existing embeds will be removed and replaced with the
          single embed generated from this function. If the supplied index is out of
          the range for the message's list of embeds, this function will simply return.
          the input message. Negative indices are also supported. Indices must be below
          `10` and above `-11`. Defaults to None.
        embed_dict (dict): The embed dictionary used for replacement.

    Returns:
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
    embed_dict: EmbedDict,
    index: int = 0,
    add_attributes: bool = True,
    edit_inner_fields: bool = False,
):
    """Edit an embed of a given message at the specified index using the given embed
    dictionary.

    Args:
        message (discord.Message): The target message.
        index (int, optional): The index of the embed to edit.
          If the supplied index is out of the range for the message's list of embeds,
          this function will simply return the input message. Negative indices are
          also supported. Defaults to 0.
        embed_dict (dict): The embed dictionary used for editing.

    Returns:
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
                embeds[index].to_dict(),
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
    update_embed_dict: dict,
    in_place: bool = True,
    add_attributes: bool = True,
    edit_inner_fields: bool = False,
) -> Optional[discord.Embed]:
    """Edit the attributes of a given embed using another dictionary.

    Args:
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
                auth["icon_url"]
                if auth.get("icon_url") is not None
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
                        inline=inline,
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
                        inline=inline,
                    )

        return

    return discord.Embed.from_dict(
        edit_embed_dict_from_dict(
            embed.to_dict(),
            update_embed_dict,
            in_place=False,
            add_attributes=add_attributes,
            edit_inner_fields=edit_inner_fields,
        )
    )


def edit_embed_dict_from_dict(
    old_embed_dict: EmbedDict,
    update_embed_dict: dict,
    in_place: bool = True,
    add_attributes: bool = True,
    edit_inner_fields: bool = False,
) -> Optional[EmbedDict]:
    """Edit the attributes of a given embed dictionary using another dictionary.

    Args:
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

    Returns:
        Optional[dict]: A new embed dictionary or `None` depending on the given
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

    return


def _read_embed_field_dict(
    field_dict: dict, allow_incomplete: bool = False, index: Optional[int] = None
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

    Args:
        embed (discord.Embed): The target embed.
        in_place (bool, optional): Whether to do this operation on the given embed
          "in place" and to return `None` instead of a new embed. Defaults to True.

    Returns:
        Optional[discord.Embed]: A new embed or `None` depending on the given
          arguments.

    Raises:
        TypeError: Invalid argument types.
        ValueError: Invalid argument structure.
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
            inline=inline,
        )

    if not in_place:
        return embed

    return


def insert_embed_fields_from_dicts(
    embed: discord.Embed, index: int, *field_dicts: dict, in_place: bool = True
) -> Optional[discord.Embed]:
    """Insert embed fields to an embed at a specified index from the given
    embed field dictionaries.

    Args:
        embed (discord.Embed): The target embed.
        index (int): The index to insert the fields at.
        *field_dicts (dict): The embed field dictionaries.
        in_place (bool, optional): Whether to do this operation on the given embed
          "in place" and to return `None` instead of a new embed. Defaults to True.

    Returns:
        Optional[discord.Embed]: A new embed or `None` depending on the given
          arguments.
    """
    fields_count = len(embed.fields)
    index = fields_count + index if index < 0 else index

    if not in_place:
        embed = embed.copy()

    for i, field in enumerate(field_dicts):
        print(field)
        name, value, inline = _read_embed_field_dict(field_dict=field, index=i)
        embed.insert_field_at(
            index,
            name=name,
            value=value,
            inline=inline,
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

    if 0 <= index < fields_count:
        old_field_dict = embed_dict["fields"][index].copy()

        for k in field_dict:
            if k in old_field_dict and field_dict[k] is not None:
                old_field_dict[k] = field_dict[k]

        embed.set_field_at(
            index,
            name=old_field_dict["name"],
            value=old_field_dict["value"],
            inline=old_field_dict["inline"],
        )

    if not in_place:
        return embed

    return


def edit_embed_fields_from_dicts(
    embed: discord.Embed, *field_dicts: dict, in_place: bool = True
) -> Optional[discord.Embed]:
    """
    Edits embed fields in the embed of a message from dictionaries
    """

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
                inline=old_field_dict["inline"],
            )

    if not in_place:
        return embed

    return


async def remove_embed_fields(
    embed: discord.Embed, *field_indices: int, in_place: bool = True
) -> Optional[discord.Embed]:
    """
    Removes multiple embed fields of the embed of a message from a
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
    """
    Swaps two embed fields of the embed of a message from a
    dictionary
    """

    if not in_place:
        embed = embed.copy()

    fields_count = len(embed.fields)
    index_a = fields_count + index_a if index_a < 0 else index_a
    index_b = fields_count + index_b if index_b < 0 else index_b

    embed_dict = embed.to_dict()
    fields_list = embed_dict["fields"]
    fields_list[index_a], fields_list[index_b] = (
        fields_list[index_b],
        fields_list[index_a],
    )

    if not in_place:
        return embed

    return


async def clone_embed_field(embed: discord.Embed, index: int, in_place: bool = True):
    """
    Duplicates an embed field
    """

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
    """
    Duplicates multiple embed fields of the embed of a message
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
    """
    Import embed data from a file or a string containing JSON
    or a Python dictionary and return it as a Python dictionary or string.
    """

    if input_format.upper() in ("JSON", "JSON_STRING"):

        if input_format.upper() == "JSON_STRING":
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
                raise TypeError("invalid source, must be an io.StringIO object")

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
                    ).with_traceback(e)

                if not isinstance(data, dict) and output_format.upper() == "DICTIONARY":
                    raise TypeError(
                        f"the file at '{source}' must be of type dict"
                        f", not '{type(data)}'"
                    )
        elif input_format == "FILE_PATH":
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
                        ).with_traceback(e)

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
    """
    Export embed data to serialized JSON or a Python dictionary and store it in a file or a string.
    """

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
