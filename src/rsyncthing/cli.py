#!/usr/bin/env -S uv run
# (c) 2026 Kimberly Wilber and the rsyncthing contributors

from dataclasses import dataclass, field
import json
from typing import Annotated, Optional
from pydantic import BaseModel
from rich import print

import asyncssh
import cyclopts
import httpx
app = cyclopts.App()


class Conn(BaseModel):
    connection_string: str
    syncthing_binary: Annotated[
        Optional[str], cyclopts.Parameter(name="--syncthing-binary", required=False, accepts_keys=True)
    ]


@app.command
def watch():
    print("Watching for changes...")

@app.command(alias="share")
def cp(src: Conn|str, dst: Conn|str):
    return [src, dst]
