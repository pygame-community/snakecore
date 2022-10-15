"""This file is a part of the source code for snakecore.
This project has been licensed under the MIT license.
Copyright (c) 2022-present pygame-community

This file defines some helpful constructs for implementing message pagination on
Discord.
"""

import asyncio
import time
from typing import Iterable, Optional, Sequence, Union

import discord
from snakecore import config, constants
from snakecore.constants import UNSET

from snakecore.utils import embeds


class EmbedPaginator:
    """An asynchronous paginator class for browsing through embeds using
    a Discord message.
    """

    def __init__(
        self,
        message: discord.Message,
        *pages: discord.Embed,
        caller: Optional[Union[discord.Member, Sequence[discord.Member]]] = None,
        whitelisted_role_ids: Optional[Iterable[int]] = None,
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
            caller (Optional[Union[discord.Member, Sequence[discord.Member]]], optional):
              The member(s) that can control the embed. A value of `None` means that
              everyone can control it. Defaults to None.
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

        self._message = message
        self._pages = list(pages)
        self._theme_color = min(max(0, int(theme_color)), 0xFFFFFF)

        self._current_page_index = max(int(start_page_number) - 1, 0)
        self._inactivity_timeout = None

        if inactivity_timeout:
            self._inactivity_timeout = int(inactivity_timeout)

        self._paginator_info_embed = embeds.create_embed(
            color=self._theme_color,
            footer_text=f"Page {self._current_page_index+1} of {len(self._pages)}.",
        )
        self._show_tutorial = False

        self._control_emojis = {
            "prev": ("◀️", "Go to the previous page"),
            "stop": ("⏹️", "Deactivate the buttons"),
            "info": ("ℹ️", "Show this information page"),
            "next": ("▶️", "Go to the next page"),
        }

        if len(self._pages) >= 3:
            self._control_emojis = {
                "first": ("⏪", "Go to the first page"),
                "prev": ("◀️", "Go to the previous page"),
                "stop": ("⏹️", "Deactivate the buttons"),
                "info": ("ℹ️", "Show this information page"),
                "next": ("▶️", "Go to the next page"),
                "last": ("⏩", "Go to the last page"),
            }
        else:
            self._control_emojis = {
                "prev": ("◀️", "Go to the previous page"),
                "stop": ("⏹️", "Deactivate the buttons"),
                "info": ("ℹ️", "Show this information page"),
                "next": ("▶️", "Go to the next page"),
            }

        self._tutorial_embed = discord.Embed(
            title="Rich Embed Paginator",
            description="".join(
                f"{emoji}: {desc}\n" for emoji, desc in self._control_emojis.values()
            ),
            color=self._theme_color,
        )

        self._current_event_task: Optional[
            asyncio.Task[discord.RawReactionActionEvent]
        ] = None

        self._is_running = True
        self._stopped = False
        self._told_to_stop = False

        self._callers = None

        if isinstance(caller, discord.Member):
            self._callers = (caller,)
        elif isinstance(caller, Sequence):
            self._callers = tuple(caller)

        self._whitelisted_role_ids = (
            set(whitelisted_role_ids) if whitelisted_role_ids is not None else None
        )

        self._stop_futures: list[asyncio.Future[bool]] = []

    @property
    def message(self):
        return self._message

    @property
    def pages(self):
        return self._pages

    @property
    def callers(self):
        return self._callers

    @property
    def whitelisted_role_ids(self):
        return self._whitelisted_role_ids

    @property
    def current_page_number(self):
        return self._current_page_index + 1

    @property
    def current_page(self):
        return self._pages[self._current_page_index]

    @property
    def inactivity_timeout(self):
        return self._inactivity_timeout

    @property
    def theme_color(self):
        return self._theme_color

    async def load_control_emojis(self):
        """Add the control reactions to the message."""
        if self._message.reactions:
            await self._message.clear_reactions()

        for emoji in self._control_emojis.values():
            if emoji[0]:
                await self._message.add_reaction(emoji[0])

    async def handle_reaction(self, reaction: str):
        """Handle a reaction."""
        if reaction == self._control_emojis.get("next", ("",))[0]:
            self.set_page_number(self._current_page_index + 2)

        elif reaction == self._control_emojis.get("prev", ("",))[0]:
            self.set_page_number(self._current_page_index)

        elif reaction == self._control_emojis.get("first", ("",))[0]:
            self.set_page_number(1)

        elif reaction == self._control_emojis.get("last", ("",))[0]:
            self.set_page_number(len(self._pages))

        elif reaction == self._control_emojis.get("stop", ("",))[0]:
            self._told_to_stop = True
            return

        elif reaction == self._control_emojis.get("info", ("",))[0]:
            await self.toggle_tutorial_page()
            return

        await self.present_page()

    async def toggle_tutorial_page(self):
        """Toggle the information page visiblity."""
        self._show_tutorial = not self._show_tutorial
        if self._show_tutorial:
            embeds.edit_embed(
                self._paginator_info_embed,
                footer_text=f"Page {self._current_page_index+1} of {len(self._pages)}.",
            )
            msg_embeds = self._message.embeds.copy()
            msg_embeds[9:] = [self._tutorial_embed, self._paginator_info_embed]
            await self._message.edit(embeds=msg_embeds)
        else:
            await self.present_page()

    def set_page_number(self, num: int):
        """Show the page with the specified page number (1-based)."""
        self._show_tutorial = False
        self._current_page_index = (num - 1) % len(self._pages)

    async def present_page(self):
        """Present the currently set page."""
        embeds.edit_embed(
            self._paginator_info_embed,
            footer_text=f"Page {self._current_page_index+1} of {len(self._pages)}.",
        )
        msg_embeds = self._message.embeds.copy()
        msg_embeds[9:] = [
            self._pages[self._current_page_index],
            self._paginator_info_embed,
        ]
        await self._message.edit(embeds=msg_embeds)

    async def _setup(self):
        if not self._pages:
            return False

        if len(self._pages) == 1:
            self.set_page_number(1)
        else:
            self.set_page_number(self._current_page_index + 1)

        await self.present_page()
        await self.load_control_emojis()

        return True

    def check_event(self, event: discord.RawReactionActionEvent):
        """Check if the event from `raw_reaction_add` can be passed down to `handle_reaction`"""
        if not (
            event.message_id == self._message.id
            and isinstance(event.member, discord.Member)
            and not event.member.bot
        ):
            return False

        if self._callers:
            for member in self._callers:
                if member.id == event.user_id:
                    return True

        if self._whitelisted_role_ids is not None:
            for role in event.member.roles if event.member else ():
                if role.id in self._whitelisted_role_ids:
                    return True

        return False

    def update(
        self,
        *pages: discord.Embed,
        callers: Optional[Union[discord.Member, Sequence[discord.Member]]] = UNSET,
        whitelisted_role_ids: Optional[Sequence[int]] = UNSET,
        page_number: int = UNSET,
        inactivity_timeout: Optional[int] = UNSET,
        theme_color: int = UNSET,
    ):
        """Update the paginator."""
        self._pages = tuple(pages) if pages else self._pages
        self._current_page_index = min(self._current_page_index, len(self._pages) - 1)

        if inactivity_timeout is not UNSET:
            if inactivity_timeout is None:
                self._inactivity_timeout = inactivity_timeout
            else:
                self._inactivity_timeout = float(inactivity_timeout)

        if callers is not UNSET:
            if isinstance(callers, discord.Member):
                self._callers = (callers,)
            elif isinstance(callers, Sequence):
                self._callers = tuple(callers)
            elif callers is None:
                self._callers = None

        if whitelisted_role_ids is not UNSET:
            self._whitelisted_role_ids = (
                set(whitelisted_role_ids) if whitelisted_role_ids is not None else None
            )

        if theme_color is not UNSET:
            self._theme_color = min(max(0, int(theme_color)), 0xFFFFFF)

        if page_number is not None:
            self.set_page_number(int(page_number))

    def is_running(self):
        """Whether the paginator is currently running."""
        return self._is_running

    def stopped(self):
        return self._stopped

    async def stop(self):
        if not self._is_running:
            return False

        if self._current_event_task is not None and not self._current_event_task.done():
            self._current_event_task.cancel()

        self._told_to_stop = True
        fut = asyncio.get_running_loop().create_future()
        self._stop_futures.append(fut)
        await fut

    async def mainloop(
        self, client: Union[discord.Client, discord.AutoShardedClient, None] = None
    ):
        """Start the mainloop. This checks for reactions and handles them. HTTP-related
        exceptions from `discord.py` are propagated from this function.
        """

        client = client or config.conf.global_client

        self._is_running = True
        self._told_to_stop = False
        self._stopped = False

        try:
            if not await self._setup():
                self._is_running = False
                self._told_to_stop = False
                self._stopped = True
                return
        except (discord.HTTPException, asyncio.CancelledError):
            self._is_running = False
            self._told_to_stop = False
            self._stopped = True
            return

        while self._is_running:
            listening_start = time.time()
            try:
                self._current_event_task = asyncio.create_task(
                    client.wait_for(
                        "raw_reaction_add",
                        timeout=self._inactivity_timeout,
                        check=self.check_event,
                    )
                )

                event = await self._current_event_task

                await self._message.remove_reaction(
                    str(event.emoji), discord.Object(event.user_id)
                )

                if self.check_event(event):
                    await self.handle_reaction(str(event.emoji))

            except asyncio.TimeoutError:
                if (
                    self._message.edited_at is not None
                    and self._message.edited_at.timestamp() - listening_start
                    < (self._inactivity_timeout or 0)
                ):
                    self._told_to_stop = True
            except (discord.HTTPException, asyncio.CancelledError):
                self._told_to_stop = True

            if self._told_to_stop:
                self._is_running = False

        self._told_to_stop = False

        try:
            await self._message.clear_reactions()
        except (discord.HTTPException, asyncio.CancelledError):
            pass

        for fut in self._stop_futures:
            if not fut.done():
                fut.set_result(True)

        self._stop_futures.clear()

        self._stopped = True

    def __await__(self):
        return self.mainloop.__await__()
