import abc
import asyncio
import base64
import json
import re
from typing import Dict, Any, Callable, TypeVar


async def guild_fetcher(v: str, c):
    """
    Type for fetching discord guilds from ids in the config

    When used, the application_data passed to the config constructor has to be
    the discord client.
    """
    return await c.fetch_guild(int(v))


async def channel_fetcher(v: str, c):
    """
    Type for fetching discord channels from ids in the config

    When used, the application_data passed to the config constructor has to be
    the discord client.
    """
    return await c.fetch_channel(int(v))


_LINE_PATTERN = re.compile(r"([a-z0-9_.]+)\s*:\s*([a-zA-Z0-9_]+)\s*=\s*(.+)")
NONE_TYPE = lambda _, _1: None
DEFAULT_TYPES = {
    "str": (lambda v, _: str(v), False),
    "Base64": (lambda v, _: base64.b64decode(v).decode(), False),
    "Guild": (guild_fetcher, True),
    "Channel": (channel_fetcher, True),
    "int": (lambda v, _: int(v), False),
    "JSON": (lambda v, _: json.loads(v), False),
    "Regex": (lambda v, _: re.compile(v), False),
    "None": NONE_TYPE
}


class AbstractConfigSection(metaclass=abc.ABCMeta):
    @abc.abstractmethod
    def get_value(self, key: str, fallback=None):
        pass

    @abc.abstractmethod
    def get_section(self, section: str) -> "AbstractConfigSection":
        pass

    def __getattr__(self, item):
        try:
            object.__getattribute__(self, item)
        except AttributeError:
            try:
                return self.get_value(key=item)
            except KeyError:
                return ConfigSection(self, item)


class ConfigSection(AbstractConfigSection):
    def __init__(self, config: "AbstractConfigSection", section: str):
        self._config: "AbstractConfigSection" = config
        self._section: str = section

    def get_value(self, key: str, fallback=None):
        return self._config.get_value(f"{self._section}.{key}", fallback=fallback)

    def get_section(self, section: str) -> "ConfigSection":
        return ConfigSection(self, section)


CustomConfigTypes = TypeVar("CustomConfigTypes", bound=dict[str, tuple[Callable[[str, Any], Any], bool]])


class SFC(AbstractConfigSection):
    def __init__(self, path: str, application_data: Any = None, custom_types: CustomConfigTypes = None, ignore_unknown_types: bool = False):
        self.file_path: str = path
        self.application_data: Any = application_data
        self.data: Dict[str, Any] = {}
        self.types: CustomConfigTypes = {**DEFAULT_TYPES, **(custom_types or {})}
        self.ignore_unknown_types: bool = ignore_unknown_types

    async def reload(self, post_ready: bool = True):
        self.data = {}

        with open(self.file_path, "r") as f:
            lines = f.readlines()

        for line_number, line in enumerate(lines):
            line = line.strip()

            if not line or line.startswith("#"):
                continue

            match = _LINE_PATTERN.match(line)

            if not match:
                raise ValueError(f"error parsing line {line_number + 1}")

            name, type_, value = match.groups()

            if self.ignore_unknown_types:
                type_constructor, is_post_ready = self.types.get(type_, NONE_TYPE)
            else:
                if type_ not in self.types.keys():
                    raise TypeError(f"invalid config type: {type_}")

                type_constructor, is_post_ready = self.types[type_]

            if not post_ready and is_post_ready:
                continue

            value = type_constructor(value, self.application_data)

            if asyncio.iscoroutine(value):
                value = await value

            self.data[name] = value

    def get_value(self, key: str, fallback=None):
        value = self.data.get(key, fallback)
        if value is None and fallback is None:
            raise KeyError(f"there is no config value for key {key} (right now)")
        return value

    def get_section(self, section: str) -> "ConfigSection":
        return ConfigSection(self, section)
