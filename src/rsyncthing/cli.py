#!/usr/bin/env -S uv run
# (c) 2026 Kimberly Wilber and the rsyncthing contributors

from functools import cached_property
import re
from dataclasses import dataclass
import sys
from typing import Annotated

from pathlib import Path
import anyio
from cyclopts import App, Parameter
import rich
import rich.console
import rich.traceback
import rich.tree

from rsyncthing.syncthing_connection import SSHSyncThingConnection, LocalSyncThingConnection, SyncThingConnection

app = App()


@Parameter(name="*", group="Common")
@dataclass
class CommonArgs:
    quiet: Annotated[bool, Parameter(alias="-q", help="Suppress output")] = False

    @cached_property
    def console(self):
        cons = rich.console.Console(stderr=True, quiet=self.quiet, highlight=False)
        # rich.traceback.install(console=cons)
        return cons

    def error(self, message: str):
        self.console.quiet = False
        self.console.print(f"[red]Error:[/red] {message}")
        sys.exit(1)


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

    @cached_property
    def connection(self) -> SyncThingConnection:
        self.resolve_path()
        if self.host is None:
            return LocalSyncThingConnection()
        else:
            return SSHSyncThingConnection(
                host=self.host,
                username=self.user,
            )

    def resolve_path(self):
        if self.host is None:
            return Path(self.path or "").resolve()
        # remote connections require absolute paths, for now
        if self.path:
            path = Path(self.path)
            if not path.is_absolute():
                raise ValueError(f"Remote path must be absolute: {self.path}")
            return path

@app.command()
async def ls(src: str = "", common: CommonArgs = CommonArgs()):
    """List shared folders on a Syncthing instance."""
    src_loc = Location.from_string(src)
    with common.console.status("Communicating with Syncthing..."):
        await src_loc.connection.connect()
        folders = await src_loc.connection.folders()
        devices = await src_loc.connection.devices()
        if not folders:
            common.console.print("No shared folders.")
            return
        tree = rich.tree.Tree(f"On [blue]{(await src_loc.connection.me()).name}[/blue]:")
        for f in folders.values():
            t = tree.add(f"[green bold]{f.label}[/] [dim]{f.path}[/dim]")
            for d in f.devices:
                t.add(f"{devices[d.device_id].name}")
        common.console.print(tree)

@app.command(alias="share")
async def cp(src: str, /, *dest: Annotated[str, Parameter(required=True)], common: CommonArgs = CommonArgs()):
    """Share a folder from one location to one or more other locations."""
    src_loc = Location.from_string(src)
    dest_locs = [Location.from_string(d) for d in dest]

    with common.console.status("Communicating with Syncthing..."):
        async with anyio.create_task_group() as tg:
            tg.start_soon(src_loc.connection.connect)
            for d_loc in dest_locs:
                tg.start_soon(d_loc.connection.connect)

        # Are we introduced to the destination devices already?
        src_device_id = src_loc.connection.my_device_id
        for d_loc in dest_locs:
            remote_device_list = await d_loc.connection.devices()
            if src_device_id in remote_device_list:
                # check: If destination is configured to auto-accept from source,
                # we can't control the destination path.
                if remote_device_list[src_device_id].auto_accept_folders:
                    if d_loc.path is not None:
                        name = remote_device_list[src_device_id].name or src_device_id
                        common.error(f"Syncthing on '{d_loc.host}' is configured to auto-accept folders from '{name}', so we cannot control the destination path.\n\nOptions:\n1. Use the default path by copying to '{d_loc.host}:' instead of '{d_loc.host}:{d_loc.path}'\n2. Log into syncthing on '{d_loc.host}' and disable auto-accept from '{name}'")

