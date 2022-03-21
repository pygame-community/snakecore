"""
This file is a part of the source code for snakecore.
This project has been licensed under the MIT license.
Copyright (c) 2020-present PygameCommunityDiscord

This file defines some important embed related utility functions.
"""

import datetime
import io
import json
import re
from ast import literal_eval
from typing import Any, Union, Optional

import black
import discord

from .utils import recursive_dict_update, recursive_dict_delete

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

DEFAULT_EMBED_COLOR = 0xFFFFAA

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


def create_embed_mask_dict(
    attributes: str = "",
    allow_system_attributes: bool = False,
    fields_as_field_dict: bool = False,
):
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
                    "Invalid embed attribute filter string!"
                    " Sub-attributes do not propagate beyond 3 levels.",
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
                                f"`{attr[i]}` is not a valid embed (sub-)attribute name!",
                            )
                    else:
                        raise ValueError(
                            f"`{attr[i]}` is not a valid embed (sub-)attribute name!",
                        )

                elif attr[i] in all_system_attribs_set and not allow_system_attributes:
                    raise ValueError(
                        f"The given attribute `{attr[i]}` cannot be retrieved when `system_attributes=`"
                        " is set to `False`.",
                    )
                if not i:
                    if attribs_tuple.count(attr[i]):
                        raise ValueError(
                            "Invalid embed attribute filter string!"
                            f" Top level embed attribute `{attr[i]}` conflicts with its"
                            " preceding instances.",
                        )
                    elif attr[i] not in attribs_with_sub_attribs:
                        raise ValueError(
                            "Invalid embed attribute filter string!"
                            f" The embed attribute `{attr[i]}` does not have any sub-attributes!",
                        )

                    if attr[i] not in embed_mask_dict:
                        embed_mask_dict[attr[i]] = bottom_dict
                    else:
                        bottom_dict = embed_mask_dict[attr[i]]

                elif i == 1 and attr[i - 1] == "fields" and not attr[i].isnumeric():
                    if attr[i].startswith("(") and attr[i].endswith(")"):
                        if not attr[i].startswith("(") and not attr[i].endswith(")"):
                            raise ValueError(
                                "Invalid embed attribute filter string!"
                                " Embed field ranges should only contain integers"
                                " and should be structured like this: "
                                "`fields.(start, stop[, step]).attribute`",
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
                                    "Invalid embed attribute filter string!"
                                    " Embed field ranges should only contain integers"
                                    " and should be structured like this: "
                                    "`fields.(start, stop[, step]).attribute`",
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
                                "Invalid embed attribute filter string!"
                                " Empty field range!",
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
                                "Invalid embed attribute filter string!"
                                f" The given attribute `{attr[i]}` is not an attribute of an embed field!",
                            )
                        break
                    else:
                        raise ValueError(
                            "Invalid embed attribute filter string!"
                            " Embed field attibutes must be either structutred like"
                            " `fields.0`, `fields.0.attribute`, `fields.attribute` or"
                            " `fields.(start,stop[,step]).attribute`. Note that embed"
                            " field ranges cannot contain whitespace.",
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
                    "Invalid embed attribute filter string!"
                    " Do not specify top level embed attributes"
                    f" twice when not using the `.` operator: `{attr}`",
                )
            elif attr in all_system_attribs_set and not allow_system_attributes:
                raise ValueError(
                    f"The given attribute `{attr}` cannot be retrieved when `system_attributes=`"
                    " is set to `False`.",
                )

            if attr not in embed_mask_dict:
                embed_mask_dict[attr] = None
            else:
                raise ValueError(
                    "Invalid embed attribute filter string!"
                    " Do not specify upper level embed attributes twice!",
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


def copy_embed(embed: discord.Embed):
    return discord.Embed.from_dict(embed.to_dict())


def handle_embed_dict_timestamp(embed_dict: dict):
    if "timestamp" in embed_dict:
        if isinstance(embed_dict["timestamp"], str):
            try:
                final_timestamp = (
                    embed_dict["timestamp"][:-1]
                    if embed_dict["timestamp"].endswith("Z")
                    else embed_dict["timestamp"]
                )
                datetime.datetime.fromisoformat(final_timestamp)
                embed_dict["timestamp"] = final_timestamp
            except ValueError:
                del embed_dict["timestamp"]
        elif isinstance(embed_dict["timestamp"], datetime.datetime):
            embed_dict["timestamp"] = embed_dict["timestamp"].isoformat()
        else:
            del embed_dict["timestamp"]

    return embed_dict


def copy_embed_dict(embed_dict: dict):
    # prevents shared reference bugs to attributes shared by the outputs of discord.Embed.to_dict()
    copied_embed_dict = {
        k: v.copy() if isinstance(v, dict) else v for k, v in embed_dict.items()
    }

    if "fields" in embed_dict:
        copied_embed_dict["fields"] = [
            field_dict.copy() for field_dict in embed_dict["fields"]
        ]
    return copied_embed_dict


def get_fields(*strings: str):
    """
    Get a list of fields from messages.
    Syntax of an embed field string: <name|value[|inline]>

    Args:
        *strings (str): The messages to get the fields from

    Returns:
        list[list[str, str, bool]]: The list of fields. if only one message is given as input, then only one field is returned.
    """
    # syntax: <Title|desc.[|inline=False]>
    field_regex = r"(<.*\|.*(\|True|\|False|\|1|\|0|)>)"
    field_datas = []
    true_bool_strings = ("", "True", "1")

    for string in strings:
        field_list = re.split(field_regex, string)
        for field in field_list:
            if field:
                field = field.strip()[1:-1]  # remove < and >
                field_data: list[Any] = field.split("|")

                if len(field_data) not in (2, 3):
                    continue
                elif len(field_data) == 2:
                    field_data.append("")

                field_data[2] = True if field_data[2] in true_bool_strings else False

                field_datas.append(field_data)

    return field_datas


def parse_condensed_embed_list(embed_list: Union[list, tuple]):
    """
    Parse the condensed embed list syntax used in some embed creation
    comnands. The syntax is:
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
            fields = get_fields(*embed_list[4])
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


def create_as_dict(
    author_name: Optional[str] = None,
    author_url: Optional[str] = None,
    author_icon_url: Optional[str] = None,
    title: Optional[str] = None,
    url: Optional[str] = None,
    thumbnail_url: Optional[str] = None,
    description: Optional[str] = None,
    image_url: Optional[str] = None,
    color: int = -1,
    fields: Union[list, tuple] = (),
    footer_text: Optional[str] = None,
    footer_icon_url: Optional[str] = None,
    timestamp: Optional[str] = None,
):
    embed_dict = {}

    if author_name or author_url or author_icon_url:
        embed_dict["author"] = {}
        if author_name:
            embed_dict["author"]["name"] = author_name
        if author_url:
            embed_dict["author"]["url"] = author_url
        if author_icon_url:
            embed_dict["author"]["icon_url"] = author_icon_url

    if footer_text or footer_icon_url:
        embed_dict["footer"] = {}
        if footer_text:
            embed_dict["footer"]["text"] = footer_text
        if footer_icon_url:
            embed_dict["footer"]["icon_url"] = footer_icon_url

    if title:
        embed_dict["title"] = title

    if url:
        embed_dict["url"] = url

    if description:
        embed_dict["description"] = description

    if color != -1:
        embed_dict["color"] = (
            int(color) if 0 <= color < 0x1000000 else DEFAULT_EMBED_COLOR
        )

    if timestamp:
        if isinstance(timestamp, str):
            try:
                datetime.datetime.fromisoformat(
                    timestamp[:-1] if timestamp.endswith("Z") else timestamp
                )
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
        for field in fields:
            field_dict = {}
            if isinstance(field, dict):
                if field.get("name", ""):
                    field_dict["name"] = field["name"]

                if field.get("value", ""):
                    field_dict["value"] = field["value"]

                if field.get("inline", "") in (False, True):
                    field_dict["inline"] = field["inline"]

            elif isinstance(field, (list, tuple)):
                name = None
                value = None
                inline = None
                field_len = len(field)
                if field_len == 3:
                    name, value, inline = field
                    if name:
                        field_dict["name"] = name

                    if value:
                        field_dict["value"] = value

                    if inline in (False, True):
                        field_dict["inline"] = inline

            if field_dict:
                fields_list.append(field_dict)

    return embed_dict


def validate_embed_dict(embed_dict: dict):
    """
    Checks if an embed dictionary can produce
    a viable embed on Discord.

    Args:
        embed_dict: The target embed dictionary

    Returns:
        A boolean indicating the validity of the
        given input dictionary.

    """
    if not embed_dict:
        return False

    embed_dict_len = len(embed_dict)
    try:
        for k, v in tuple(embed_dict.items()):
            if (
                embed_dict_len == 1
                and (k == "color" or k == "timestamp")
                or embed_dict_len == 2
                and ("color" in embed_dict and "timestamp" in embed_dict)
            ):
                return False
            elif (
                not v
                or not isinstance(v, (str, list, dict, int))
                or (k == "footer" and "text" not in v)
                or (k == "author" and "name" not in v)
                or (k in ("thumbnail", "image") and "url" not in v)
                or (k == "color" and not isinstance(v, int))
            ):
                return False

            elif k == "fields":
                if isinstance(v, list):
                    for d in v:
                        if not isinstance(d, dict) or (
                            "name" not in d or "value" not in d
                        ):
                            return False
                else:
                    return False

            elif k == "color" and not 0 <= embed_dict["color"] <= 0xFFFFFF:
                return False

            elif k == "timestamp":
                try:
                    datetime.datetime.fromisoformat(embed_dict[k])
                except ValueError:
                    return False
    except TypeError:
        return False

    return True


def clean_embed_dict(embed_dict: dict):
    """
    Cleans up an embed dictionary by deleting
    invalid attributes that would cause
    errors not related to a discord.HTTPException.

    Args:
        embed_dict: The target embed dictionary

    Returns:
        The same embed dictionary given as input

    """

    for k, v in tuple(embed_dict.items()):
        if (
            not v
            or not isinstance(v, (str, list, dict, int))
            or (k == "footer" and ("text" not in v or not isinstance(v, dict)))
            or (k == "author" and "name" not in v)
            or (k in ("thumbnail", "image") and "url" not in v)
            or (k == "color" and not isinstance(v, int))
        ):
            del embed_dict[k]

        elif k == "fields":
            if isinstance(v, list):
                for i in reversed(range(len(v))):
                    if not isinstance(v[i], dict) or (
                        "name" not in v[i] or "value" not in v[i]
                    ):
                        v.pop(i)
            else:
                del embed_dict[k]

        elif k == "color":
            embed_dict["color"] = min(max(0, embed_dict["color"]), 0xFFFFFF)

        elif k == "timestamp":
            try:
                datetime.datetime.fromisoformat(embed_dict[k])
            except ValueError:
                del embed_dict["timestamp"]

    return embed_dict


def create(
    author_name: Optional[str] = None,
    author_url: Optional[str] = None,
    author_icon_url: Optional[str] = None,
    title: Optional[str] = None,
    url: Optional[str] = None,
    thumbnail_url: Optional[str] = None,
    description: Optional[str] = None,
    image_url: Optional[str] = None,
    color: int = DEFAULT_EMBED_COLOR,
    fields: Union[list, tuple] = (),
    footer_text: Optional[str] = None,
    footer_icon_url: Optional[str] = None,
    timestamp: Optional[Union[str, datetime.datetime]] = None,
):
    """
    Creates an embed with a much more tight function.
    """
    embed = discord.Embed(
        title=title,
        url=url,
        description=description,
        color=color if 0 <= color < 0x1000000 else DEFAULT_EMBED_COLOR,
    )

    if timestamp:
        if isinstance(timestamp, str):
            try:
                embed.timestamp = datetime.datetime.fromisoformat(
                    timestamp[:-1] if timestamp.endswith("Z") else timestamp
                )
            except ValueError:
                pass
        elif isinstance(timestamp, datetime.datetime):
            embed.timestamp = timestamp

    if author_name:
        embed.set_author(name=author_name, url=author_url, icon_url=author_icon_url)

    if thumbnail_url:
        embed.set_thumbnail(url=thumbnail_url)

    if image_url:
        embed.set_image(url=image_url)

    for field in fields:
        if isinstance(field, dict):
            embed.add_field(
                name=field.get("name", ""),
                value=field.get("value", ""),
                inline=field.get("inline", True),
            )
        else:
            embed.add_field(name=field[0], value=field[1], inline=field[2])

    if footer_text:
        embed.set_footer(text=footer_text, icon_url=footer_icon_url)

    return embed


async def send(
    channel: discord.abc.Messageable,
    author_name: Optional[str] = None,
    author_url: Optional[str] = None,
    author_icon_url: Optional[str] = None,
    title: Optional[str] = None,
    url: Optional[str] = None,
    thumbnail_url: Optional[str] = None,
    description: Optional[str] = None,
    image_url: Optional[str] = None,
    color: int = DEFAULT_EMBED_COLOR,
    fields: Union[list, tuple] = (),
    footer_text: Optional[str] = None,
    footer_icon_url: Optional[str] = None,
    timestamp: Optional[str] = None,
    reference: Optional[Union[discord.Message, discord.MessageReference]] = None,
):
    """
    Sends an embed with a much more tight function. If the channel is
    None it will return the embed instead of sending it.
    """

    embed = create(
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


async def replace(
    message: discord.Message,
    author_name: Optional[str] = None,
    author_url: Optional[str] = None,
    author_icon_url: Optional[str] = None,
    title: Optional[str] = None,
    url: Optional[str] = None,
    thumbnail_url: Optional[str] = None,
    description: Optional[str] = None,
    image_url: Optional[str] = None,
    color: int = DEFAULT_EMBED_COLOR,
    fields: Union[list, tuple] = (),
    footer_text: Optional[str] = None,
    footer_icon_url: Optional[str] = None,
    timestamp: Optional[str] = None,
):
    """
    Replaces the embed of a message with a much more tight function
    """
    embed = create(
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
    return await message.edit(embed=embed)


async def edit(
    message: discord.Message,
    embed: discord.Embed,
    author_name: Optional[str] = None,
    author_url: Optional[str] = None,
    author_icon_url: Optional[str] = None,
    title: Optional[str] = None,
    url: Optional[str] = None,
    thumbnail_url: Optional[str] = None,
    description: Optional[str] = None,
    image_url: Optional[str] = None,
    color=-1,
    fields=[],
    footer_text: Optional[str] = None,
    footer_icon_url: Optional[str] = None,
    timestamp: Optional[str] = None,
    add_attributes: bool = False,
    edit_inner_fields: bool = False,
):
    """
    Updates the changed attributes of the embed of a message with a
    much more tight function
    """
    old_embed_dict = embed.to_dict()
    update_embed_dict = create_as_dict(
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

    recursive_dict_update(
        old_embed_dict, update_embed_dict, add_new_keys=add_attributes, skip_value=""
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

    if message is None:
        return discord.Embed.from_dict(old_embed_dict)

    return await message.edit(embed=discord.Embed.from_dict(old_embed_dict))


def create_from_dict(data: dict):
    """
    Creates an embed from a dictionary with a much more tight function
    """
    data = handle_embed_dict_timestamp(data)
    return discord.Embed.from_dict(data)


async def send_from_dict(channel: discord.abc.Messageable, data: dict):
    """
    Sends an embed from a dictionary with a much more tight function
    """
    return await channel.send(embed=create_from_dict(data))


async def replace_from_dict(message: discord.Message, data: dict):
    """
    Replaces the embed of a message from a dictionary with a much more
    tight function
    """
    handle_embed_dict_timestamp(data)
    return await message.edit(embed=create_from_dict(data))


async def edit_from_dict(
    message: discord.Message,
    embed: discord.Embed,
    update_embed_dict: dict,
    add_attributes: bool = True,
    edit_inner_fields: bool = False,
):
    """
    Edits the attributes of a given embed from an embed
    dictionary, and applies them as new embed to the message given as input.

    Args:
        message (discord.Message): The target message to apply the modified embed to.
        embed (discord.Embed): The target embed to make a new, modified embed from.
        update_embed_dict (dict): The embed dictionary used for modification.
        add_attributes (bool, optional): Whether the embed attributes in 'update_embed_dict'
          should be added to the new modified embed if not present. Defaults to True.
        edit_inner_fields (bool, optional): Whether to modify the 'fields' attribute of an embed
          as one unit or to modify the embeds fields themselves, one by one. Defaults to False.
    """
    old_embed_dict = embed.to_dict()

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

    recursive_dict_update(
        old_embed_dict, update_embed_dict, add_new_keys=add_attributes, skip_value=""
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

    old_embed_dict = handle_embed_dict_timestamp(old_embed_dict)

    return await message.edit(embed=discord.Embed.from_dict(old_embed_dict))


def edit_dict_from_dict(
    old_embed_dict: dict,
    update_embed_dict: dict,
    add_attributes: bool = True,
    edit_inner_fields: bool = False,
):
    """
    Edits the changed attributes of an embed dictionary using another
    dictionary
    """
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

    recursive_dict_update(
        old_embed_dict, update_embed_dict, add_new_keys=add_attributes, skip_value=""
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

    old_embed_dict = handle_embed_dict_timestamp(old_embed_dict)

    return old_embed_dict


async def replace_field_from_dict(
    message: discord.Message, embed: discord.Embed, field_dict: dict, index: int
):
    """
    Replaces an embed field of the embed of a message from a dictionary
    """

    fields_count = len(embed.fields)
    index = fields_count + index if index < 0 else index

    embed.set_field_at(
        index,
        name=field_dict.get("name", ""),
        value=field_dict.get("value", ""),
        inline=field_dict.get("inline", True),
    )

    return await message.edit(embed=embed)


async def edit_field_from_dict(
    message: discord.Message, embed: discord.Embed, field_dict: dict, index: int
):
    """
    Edits parts of an embed field of the embed of a message from a
    dictionary
    """

    fields_count = len(embed.fields)
    index = fields_count + index if index < 0 else index
    embed_dict = embed.to_dict()

    old_field_dict = embed_dict["fields"][index]

    for k in field_dict:
        if k in old_field_dict and field_dict[k] != "":
            old_field_dict[k] = field_dict[k]

    embed.set_field_at(
        index,
        name=old_field_dict.get("name", ""),
        value=old_field_dict.get("value", ""),
        inline=old_field_dict.get("inline", True),
    )

    return await message.edit(embed=embed)


async def edit_fields_from_dicts(
    message: discord.Message, embed: discord.Embed, field_dicts: list[dict]
):
    """
    Edits embed fields in the embed of a message from dictionaries
    """

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
                if k in old_field_dict and field_dict[k] != "":
                    old_field_dict[k] = field_dict[k]

            embed.set_field_at(
                i,
                name=old_field_dict.get("name", ""),
                value=old_field_dict.get("value", ""),
                inline=old_field_dict.get("inline", True),
            )

    return await message.edit(embed=embed)


async def add_field_from_dict(
    message: discord.Message, embed: discord.Embed, field_dict: dict
):
    """
    Adds an embed field to the embed of a message from a dictionary
    """

    embed.add_field(
        name=field_dict.get("name", ""),
        value=field_dict.get("value", ""),
        inline=field_dict.get("inline", True),
    )
    return await message.edit(embed=embed)


async def add_fields_from_dicts(
    message: discord.Message, embed: discord.Embed, field_dicts: list[dict]
):
    """
    Adds embed fields to the embed of a message from dictionaries
    """

    for field_dict in field_dicts:
        embed.add_field(
            name=field_dict.get("name", ""),
            value=field_dict.get("value", ""),
            inline=field_dict.get("inline", True),
        )

    return await message.edit(embed=embed)


async def insert_field_from_dict(
    message: discord.Message, embed: discord.Embed, field_dict: dict, index: int
):
    """
    Inserts an embed field of the embed of a message from a
    """

    fields_count = len(embed.fields)
    index = fields_count + index if index < 0 else index
    embed.insert_field_at(
        index,
        name=field_dict.get("name", ""),
        value=field_dict.get("value", ""),
        inline=field_dict.get("inline", True),
    )
    return await message.edit(embed=embed)


async def insert_fields_from_dicts(
    message: discord.Message, embed: discord.Embed, field_dicts: list[dict], index: int
):
    """
    Inserts embed fields to the embed of a message from dictionaries
    at a specified index
    """
    fields_count = len(embed.fields)
    index = fields_count + index if index < 0 else index
    for field_dict in field_dicts:
        embed.insert_field_at(
            index,
            name=field_dict.get("name", ""),
            value=field_dict.get("value", ""),
            inline=field_dict.get("inline", True),
        )

    return await message.edit(embed=embed)


async def remove_fields(
    message: discord.Message, embed: discord.Embed, field_indices: list
):
    """
    Removes multiple embed fields of the embed of a message from a
    dictionary
    """

    fields_count = len(embed.fields)

    parsed_field_indices = [
        fields_count + idx if idx < 0 else idx for idx in field_indices
    ]

    parsed_field_indices.sort(reverse=True)

    for index in parsed_field_indices:
        embed.remove_field(index)

    return await message.edit(embed=embed)


async def swap_fields(
    message: discord.Message, embed: discord.Embed, index_a: int, index_b: int
):
    """
    Swaps two embed fields of the embed of a message from a
    dictionary
    """

    fields_count = len(embed.fields)
    index_a = fields_count + index_a if index_a < 0 else index_a
    index_b = fields_count + index_b if index_b < 0 else index_b

    embed_dict = embed.to_dict()
    fields_list = embed_dict["fields"]
    fields_list[index_a], fields_list[index_b] = (
        fields_list[index_b],
        fields_list[index_a],
    )

    return await message.edit(embed=discord.Embed.from_dict(embed_dict))


async def clone_field(message: discord.Message, embed: discord.Embed, index: int):
    """
    Duplicates an embed field of the embed of a message from a
    dictionary
    """
    fields_count = len(embed.fields)
    index = fields_count + index if index < 0 else index

    embed_dict = embed.to_dict()
    cloned_field = embed_dict["fields"][index].copy()
    embed_dict["fields"].insert(index, cloned_field)

    return await message.edit(embed=discord.Embed.from_dict(embed_dict))


async def clone_fields(
    message: discord.Message,
    embed: discord.Embed,
    field_indices: list,
    insertion_index: Optional[int] = None,
):
    """
    Duplicates multiple embed fields of the embed of a message
    from a dictionary
    """

    fields_count = len(embed.fields)

    parsed_field_indices = [
        fields_count + idx if idx < 0 else idx for idx in field_indices
    ]

    parsed_field_indices.sort(reverse=True)

    embed_dict = embed.to_dict()

    if isinstance(insertion_index, int):
        insertion_index = (
            fields_count + insertion_index if insertion_index < 0 else insertion_index
        )
        cloned_fields = tuple(
            embed_dict["fields"][index].copy()
            for index in sorted(field_indices, reverse=True)
        )
        for cloned_field in cloned_fields:
            embed_dict["fields"].insert(insertion_index, cloned_field)
    else:
        for index in parsed_field_indices:
            cloned_field = embed_dict["fields"][index].copy()
            embed_dict["fields"].insert(index, cloned_field)

    return await message.edit(embed=discord.Embed.from_dict(embed_dict))


async def clear_fields(
    message: discord.Message,
    embed: discord.Embed,
):
    """
    Removes all embed fields of the embed of a message from a
    dictionary
    """
    embed.clear_fields()
    return await message.edit(embed=embed)


def import_embed_data(
    source: Union[str, io.StringIO],
    from_string: bool = False,
    from_json: bool = False,
    from_json_string: bool = False,
    as_string: bool = False,
    as_dict: bool = True,
):
    """
    Import embed data from a file or a string containing JSON
    or a Python dictionary and return it as a Python dictionary or string.
    """

    if from_json or from_json_string:

        if from_json_string:
            json_data = json.loads(source)

            if not isinstance(json_data, dict) and as_dict:
                raise TypeError(
                    "The given string must contain a JSON object that"
                    " can be converted into a Python `dict` object"
                )
            if as_string:
                json_data = json.dumps(json_data)

            return json_data

        else:
            json_data = json.load(source)

            if not isinstance(json_data, dict) and as_dict:
                raise TypeError(
                    f"the file at '{source}' must contain a JSON object that"
                    " can be converted into a Python `dict` object"
                )
            if as_string:
                json_data = json.dumps(json_data)

            return json_data

    elif from_string:
        try:
            data = literal_eval(source)
        except Exception as e:
            raise TypeError(
                "The contents of the given object must be parsable into literal Python "
                "strings, bytes, numbers, tuples, lists, dicts, sets, booleans, and "
                "None."
            ).with_traceback(e)

        if not isinstance(data, dict) and as_dict:
            raise TypeError(
                f"the file at '{source}' must be of type dict" f", not '{type(data)}'"
            )

        if as_string:
            return repr(data)

        return data

    else:
        data = None
        if isinstance(source, io.StringIO):
            if as_string:
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

                if not isinstance(data, dict) and as_dict:
                    raise TypeError(
                        f"the file at '{source}' must be of type dict"
                        f", not '{type(data)}'"
                    )
        else:
            with open(source, "r", encoding="utf-8") as d:
                if as_string:
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

                    if not isinstance(data, dict) and as_dict:
                        raise TypeError(
                            f"the file at '{source}' must be of type dict"
                            f", not '{type(data)}'"
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
