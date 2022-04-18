"""This file is a part of the source code for snakecore.
This project has been licensed under the MIT license.
Copyright (c) 2022-present PygameCommunityDiscord

This file defines some helpful constructs for implementing message pagination on
Discord.
"""

import asyncio
from tkinter import N
from typing import Optional, Sequence, Union

import discord
from snakecore import config

from snakecore.utils import embed_utils


class EmbedPaginator:
    """An asynchronous paginator class for browsing through embeds using
    a Discord message.
    """

    def __init__(
        self,
        message: discord.Message,
        *pages: discord.Embed,
        caller: Optional[Union[discord.Member, Sequence[discord.Member]]] = None,
        whitelisted_role_ids: Optional[Sequence[discord.Role]] = None,
        start_page_number: int = 1,
        inactivity_timeout: Optional[int] = None,
        theme_color: int = 0,
    ):
        """
        Create an embed paginator that can paginate between the given embed pages,
        using the given Discord message in a guild. The message must have remaining
        space for at least 2 embeds, otherwise the last 2 will be overwritten.

        Args:
            message (discord.Message): The message to use for pagination.
            *pages (discord.Embed): The embed pages.
            caller (Optional[discord.Member], optional): The user (or list of users)
              that can control the embed. A value of `None` means that everyone can
              control it. Defaults to None.
            whitelisted_role_ids (Optional[Sequence[discord.Role]], optional): The
              IDs of the guild roles that are always granted control over this embed
              paginator.
            start_page_number (int): The number of the page to start from (1-based).
              Defaults to 1.
            inactivity_timeout (Optional[int], optional): The maximum time period
              for this paginator to wait for a reaction to occur, before aborting.
              Defaults to None.
            theme_color (int): The theme color integer to use for all extra embeds
              used by the paginator. Defaults to 0.
        """

        self.message = message
        self.pages = list(pages)
        self.theme_color = min(max(0, int(theme_color)), 0xFFFFFF)
        self.current_page_index = max(int(start_page_number) - 1, 0)
        self.inactivity_timeout = None

        if inactivity_timeout:
            self.inactivity_timeout = int(inactivity_timeout)

        self.paginator_info_embed = embed_utils.create_embed(
            color=self.theme_color,
            footer_text=f"Page {self.current_page_index+1} of {len(self.pages)}.",
        )
        self.show_tutorial = False

        self.control_emojis = {
            "prev": ("◀️", "Go to the previous page"),
            "stop": ("⏹️", "Deactivate the buttons"),
            "info": ("ℹ️", "Show this information page"),
            "next": ("▶️", "Go to the next page"),
        }

        if len(self.pages) >= 3:
            self.control_emojis = {
                "first": ("⏪", "Go to the first page"),
                "prev": ("◀️", "Go to the previous page"),
                "stop": ("⏹️", "Deactivate the buttons"),
                "info": ("ℹ️", "Show this information page"),
                "next": ("▶️", "Go to the next page"),
                "last": ("⏩", "Go to the last page"),
            }
        else:
            self.control_emojis = {
                "prev": ("◀️", "Go to the previous page"),
                "stop": ("⏹️", "Deactivate the buttons"),
                "info": ("ℹ️", "Show this information page"),
                "next": ("▶️", "Go to the next page"),
            }

        self.tutorial_embed = discord.Embed(
            title="Rich Embed Paginator",
            description="".join(
                f"{emoji}: {desc}\n" for emoji, desc in self.control_emojis.values()
            ),
            color=self.theme_color,
        )

        self.stopped = False
        self.callers = None

        if isinstance(caller, discord.Member):
            self.callers = (caller,)
        elif isinstance(caller, Sequence):
            self.callers = tuple(caller)

        self.whitelisted_role_ids = (
            {int(i) for i in whitelisted_role_ids}
            if whitelisted_role_ids is not None
            else None
        )

    async def load_control_emojis(self):
        """Add the control reactions to the message."""
        if self.message.reactions:
            await self.message.clear_reactions()

        for emoji in self.control_emojis.values():
            if emoji[0]:
                await self.message.add_reaction(emoji[0])

    async def handle_reaction(self, reaction: str):
        """Handle a reaction."""
        if reaction == self.control_emojis.get("next", ("",))[0]:
            self.set_page_number(self.current_page_index + 2)

        elif reaction == self.control_emojis.get("prev", ("",))[0]:
            self.set_page_number(self.current_page_index)

        elif reaction == self.control_emojis.get("first", ("",))[0]:
            self.set_page_number(1)

        elif reaction == self.control_emojis.get("last", ("",))[0]:
            self.set_page_number(len(self.pages))

        elif reaction == self.control_emojis.get("stop", ("",))[0]:
            self.stopped = True
            return

        elif reaction == self.control_emojis.get("info", ("",))[0]:
            await self.toggle_tutorial_page()
            return

        await self.present_page()

    async def toggle_tutorial_page(self):
        """Toggle the information page visiblity."""
        self.show_tutorial = not self.show_tutorial
        if self.show_tutorial:
            embed_utils.edit_embed(
                self.paginator_info_embed,
                footer_text=f"Page {self.current_page_index+1} of {len(self.pages)}.",
            )
            embeds = self.message.embeds.copy()
            embeds[9:] = [self.tutorial_embed, self.paginator_info_embed]
            await self.message.edit(embeds=embeds)
        else:
            await self.present_page()

    def set_page_number(self, num: int):
        """Show the page with the specified page number (1-based)."""
        self.show_tutorial = False
        self.current_page_index = (num - 1) % len(self.pages)

    async def present_page(self):
        """Present the currently set page."""
        embed_utils.edit_embed(
            self.paginator_info_embed,
            footer_text=f"Page {self.current_page_index+1} of {len(self.pages)}.",
        )
        embeds = self.message.embeds.copy()
        embeds[9:] = [self.pages[self.current_page_index], self.paginator_info_embed]
        await self.message.edit(embeds=embeds)

    async def _setup(self):
        if not self.pages:
            return False

        if len(self.pages) == 1:
            self.set_page_number(1)
        else:
            self.set_page_number(self.current_page_index + 1)

        await self.present_page()
        await self.load_control_emojis()

        return True

    def check_event(self, event: discord.RawReactionActionEvent):
        """Check if the event from `raw_reaction_add` can be passed down to `handle_reaction`"""

        if self.callers:

            for member in self.callers:
                if member.id == event.user_id:
                    return True

        if self.whitelisted_role_ids is not None:
            for role in event.member.roles:
                if role.id in self.whitelisted_role_ids:
                    return True

        return False

    def prepare_resume(self):
        """Prepare the paginator to resume where it left off."""
        self.stopped = False

    async def mainloop(self):
        """Start the mainloop. This checks for reactions and handles them. HTTP-related
        exceptions from `discord.py` are propagated from this function.
        """
        if not await self._setup():
            return

        while not self.stopped:
            try:
                event = await config.conf.global_client.wait_for(
                    "raw_reaction_add",
                    timeout=self.inactivity_timeout,
                    check=(
                        lambda event: event.message_id == self.message.id
                        and isinstance(event.member, discord.Member)
                        and not event.member.bot
                    ),
                )

                await self.message.remove_reaction(str(event.emoji), event.member)

                if self.check_event(event):
                    await self.handle_reaction(str(event.emoji))

            except asyncio.TimeoutError:
                self.stopped = True

        await self.message.clear_reactions()
