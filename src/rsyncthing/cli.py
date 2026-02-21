#!/usr/bin/env -S uv run
# (c) 2026 Kimberly Wilber and the rsyncthing contributors

import re
from dataclasses import dataclass
from typing import Annotated

from pathlib import Path
from xml.dom.minidom import Notation
from cyclopts import App, Parameter

from rsyncthing.syncthing_connection import SSHSyncThingConnection, LocalSyncThingConnection

app = App()

location_re = re.compile(r"""
    ^(?:
        (?: (?P<user>[^@/:\s]+) @ )? # username@
            (?P<host>
                \[ [^\]]+ \] # either ipv6-literal
                | [^/:\s]+ # or regular host
            ) :
        )?
        (?P<path>.*) $
    """,
    re.VERBOSE,
)

@dataclass
class Location:
    user: str | None
    host: str | None
    path: str | None

    @classmethod
    def from_string(cls, s: str) -> "Location":
        if (m := location_re.match(s)):
            return cls(
                user=m.group("user") or None,
                host=m.group("host") or None,
                path=m.group("path") or None,
            )
        raise ValueError(f"Invalid location string: {s}")

    def to_connection(self):
        if self.host is None:
            return LocalSyncThingConnection()
        else:
            return SSHSyncThingConnection(
                host=self.host,
                username=self.user,
            )

    def to_path(self):
        if self.host is None:
            return Path(self.path or "").resolve()
        # remote connections require absolute paths, for now
        path = Path(self.path)
        if not path.is_absolute():
            raise ValueError(f"Remote path must be absolute: {self.path}")
        return path

@app.command(alias="share")
async def cp(src: str, /, *dest: Annotated[str, Parameter(required=True)]):
    """Share a folder from one location to one or more other locations."""
    src_loc = Location.from_string(src)
    dest_locs = [Location.from_string(d) for d in dest]

    src_conn = src_loc.to_connection()
    dest_conns = [d.to_connection() for d in dest_locs]

    await src_conn.connect()
    for c in dest_conns:
        await c.connect()

