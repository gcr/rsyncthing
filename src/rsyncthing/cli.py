#!/usr/bin/env -S uv run
# (c) 2026 Kimberly Wilber and the rsyncthing contributors

from dataclasses import dataclass, field
import json

import asyncssh
import cyclopts
import httpx
app = cyclopts.App()



@app.command
def watch():
    print("Watching for changes...")

@app.command
def cp():
    print("Hello from Cyclopts")
