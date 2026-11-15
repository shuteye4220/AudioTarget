"""Spoken menu navigation (pure logic; speech is injected)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Awaitable, Callable, Union

from .keys import Action

Label = Union[str, Callable[[], str]]


@dataclass
class Item:
    label: Label
    action: Callable[[], Awaitable[None]] | None = None
    # A submenu, or a coroutine that builds one (for lists found at run time).
    submenu: "Menu | Callable[[], Awaitable[Menu]] | None" = None

    def text(self) -> str:
        return self.label() if callable(self.label) else self.label


@dataclass
class Menu:
    title: str
    items: list[Item] = field(default_factory=list)
    empty_text: str = "Nothing here."


Say = Callable[[str], Awaitable[None]]


class Navigator:
    def __init__(self, root: Menu, say: Say) -> None:
        self.root = root
        self.say = say
        self.stack: list[tuple[Menu, int]] = [(root, 0)]

    @property
    def menu(self) -> Menu:
        return self.stack[-1][0]

    @property
    def index(self) -> int:
        return self.stack[-1][1]

    def _set_index(self, i: int) -> None:
        self.stack[-1] = (self.menu, i)

    def current_text(self) -> str:
        m = self.menu
        if not m.items:
            return m.empty_text
        return f"{m.items[self.index].text()}. {self.index + 1} of {len(m.items)}"

    async def announce(self) -> None:
        await self.say(f"{self.menu.title}. {self.current_text()}")

    async def open(self, menu: Menu) -> None:
        self.stack.append((menu, 0))
        await self.announce()

    async def handle(self, action: Action) -> None:
        m = self.menu
        if action is Action.HOME:
            self.stack = [(self.root, 0)]
            await self.announce()
        elif action is Action.BACK:
            if len(self.stack) > 1:
                self.stack.pop()
                await self.say(f"{self.menu.title}. {self.current_text()}")
            else:
                await self.say(f"Top menu. {self.current_text()}")
        elif action in (Action.UP, Action.DOWN) and m.items:
            step = -1 if action is Action.UP else 1
            self._set_index((self.index + step) % len(m.items))
            await self.say(self.current_text())
        elif action is Action.SELECT and m.items:
            item = m.items[self.index]
            if item.submenu is not None:
                sub = item.submenu if isinstance(item.submenu, Menu) else await item.submenu()
                await self.open(sub)
            elif item.action is not None:
                await item.action()
        elif not m.items:
            await self.say(m.empty_text)
