"""This file is a part of the source code for snakecore.
This project has been licensed under the MIT license.
Copyright (c) 2022-present PygameCommunityDiscord

This file defines some helpful constructs for implementing message pagination on
Discord.
"""

import asyncio
from typing import Optional, Sequence, Union

import discord
from snakecore import config

from snakecore.utils import embed_utils


class EmbedPaginator:
    def __init__(
        self,
        message: discord.Message,
        *pages: discord.Embed,
        caller: Optional[Union[discord.Member, Sequence[discord.Member]]] = None,
        whitelisted_roles: Optional[Sequence[discord.Role]] = None,
        start_page: int = 0,
    ):
        """
        Create an embed which can be controlled by reactions. The footer of the
        embeds will be overwritten. If the optional "command" argument
        is set the embed page will be refreshable. The pages argument must
        have at least one embed.

        Args:
            message (discord.Message): The message to overwrite.
            *pages (list[discord.Embed]): The embeds to change
              pages between.
            caller (Optional[discord.Member], optional): The user (or list of users) that can
              control the embed. A value of `None` means that everyone can control it.
              Defaults to None.
            whitelisted_roles (Optional[Sequence[discord.Role]], optional): The guild
              roles that are always granted control over this embed paginator.

            start_page (int): The page to start from. Defaults to 0.
        """
        self.pages = list(pages)
        self.current_page = start_page
        self.message = message
        self.is_on_info = False

        self.control_emojis = {
            "first": ("", ""),
            "prev": ("◀️", "Go to the previous page"),
            "stop": ("⏹️", "Deactivate the buttons"),
            "info": ("ℹ️", "Show this information page"),
            "next": ("▶️", "Go to the next page"),
            "last": ("", ""),
        }

        if len(self.pages) >= 3:
            self.control_emojis["first"] = ("⏪", "Go to the first page")
            self.control_emojis["last"] = ("⏩", "Go to the last page")

        self.killed = False
        self.callers = None

        if isinstance(caller, discord.Member):
            self.callers = (caller,)
        elif isinstance(caller, Sequence):
            self.callers = tuple(caller)

        self.whitelisted_role_ids = {role.id for role in whitelisted_roles}

        self.help_text = ""
        for emoji, desc in self.control_emojis.values():
            if emoji:
                self.help_text += f"{emoji}: {desc}\n"

    async def add_control_emojis(self):
        """Add the control reactions to the message."""
        for emoji in self.control_emojis.values():
            if emoji[0]:
                await self.message.add_reaction(emoji[0])

    async def handle_reaction(self, reaction: str):
        """Handle a reaction."""
        if reaction == self.control_emojis.get("next", ("",))[0]:
            await self.set_page(self.current_page + 1)

        if reaction == self.control_emojis.get("prev", ("",))[0]:
            await self.set_page(self.current_page - 1)

        if reaction == self.control_emojis.get("first", ("",))[0]:
            await self.set_page(0)

        if reaction == self.control_emojis.get("last", ("",))[0]:
            await self.set_page(len(self.pages) - 1)

        if reaction == self.control_emojis.get("stop", ("",))[0]:
            self.killed = True

        if reaction == self.control_emojis.get("info", ("",))[0]:
            await self.show_info_page()

    async def show_info_page(self, page_color: int = 0):
        """Create and show the info page."""
        self.is_on_info = not self.is_on_info
        if self.is_on_info:
            info_page_embed = embed_utils.create_embed(
                description=self.help_text,
                color=page_color,
                footer_text=self.get_footer_text(self.current_page),
            )
            await self.message.edit(embed=info_page_embed)
        else:
            await self.message.edit(embed=self.pages[self.current_page])

    async def set_page(self, num: int):
        """Set the current page and display it."""
        self.is_on_info = False
        self.current_page = num % len(self.pages)
        await self.message.edit(embed=self.pages[self.current_page])

    async def _setup(self):
        if not self.pages:
            await embed_utils.replace_embed_at(
                self.message,
                index=None,
                title="Internal error occured!",
                description="Got empty embed list for PagedEmbed",
                color=0xFF0000,
            )
            return False

        if len(self.pages) == 1:
            await self.message.edit(embed=self.pages[0])
            return False

        for i, page in enumerate(self.pages):
            footer = self.get_footer_text(i)

            page.set_footer(text=footer)

        await self.message.edit(embed=self.pages[self.current_page])
        await self.add_control_emojis()

        return True

    def get_footer_text(self, page_num: int):
        """Get the information footer text, which contains the current page."""
        footer = f"Page {page_num + 1} of {len(self.pages)}.\n"
        return footer

    async def filter_event(self, event: discord.RawReactionActionEvent):
        """Check if the event from `raw_reaction_add` can be passed down to `handle_reaction`"""
        if (
            event.message_id != self.message.id
            or not isinstance(event.member, discord.Member)
            or event.member.bot
        ):
            return False

        await self.message.remove_reaction(str(event.emoji), event.member)
        if self.callers:
            for member in self.callers:
                if member.id == event.user_id:
                    return True

            for role in event.member.roles:
                if role.id in self.whitelisted_role_ids:
                    return True

    async def mainloop(self):
        """Start the mainloop. This checks for reactions and handles them."""
        if not await self._setup():
            return

        while not self.killed:
            try:
                event = await config.conf.global_client.wait_for(
                    "raw_reaction_add", timeout=60
                )

                if await self.check(event):
                    await self.handle_reaction(str(event.emoji))

            except asyncio.TimeoutError:
                self.killed = True

        await self.message.clear_reactions()
