#!/usr/bin/env -S uv run
# (c) 2026 Kimberly Wilber and the rsyncthing contributors

from dataclasses import dataclass, field
import json
from typing import Annotated
from pydantic import BaseModel
from rich import print

import asyncssh
import cyclopts
import httpx
app = cyclopts.App()


@cyclopts.Parameter(converter="parse_conn_string")
class Conn(BaseModel):
    host: str | None
    path: str

    @cyclopts.Parameter(n_tokens=1, accepts_keys=True)
    @classmethod
    def parse_conn_string(cls, tokens):
        print(tokens)
        tok = tokens[0]
        if ":" in tok.value:
            host, path = tok.value.split(":", 1)
            return cls(host=host, path=path)
        else:
            return cls(host=None, path=tok.value)

@app.command
def watch():
    print("Watching for changes...")

def make_converter(_type, tokens):
    print("TYPE", _type)
    print("TOK", tokens)
    return Conn(host="example.com", path="/some/path")

@app.command(alias="share")
def cp(src: Conn, dest: Conn, *dest2: Annotated[Conn,
                                                cyclopts.Parameter(converter=make_converter)]):
    return [src, dest, *dest2]
