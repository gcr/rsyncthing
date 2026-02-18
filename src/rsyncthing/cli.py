#!/usr/bin/env -S uv run
# (c) 2026 Kimberly Wilber and the rsyncthing contributors

from dataclasses import dataclass, field
import json

import asyncssh
import cyclopts
import httpx
app = cyclopts.App()

@dataclass
class SyncThingConnection:
    my_device_id: str | None = field(default=None, kw_only=True)
    syncthing_binary_path: str = field(default="syncthing", kw_only=True)
    _http_client: httpx.AsyncClient | None = field(init=False, default=None)

    def is_connected(self) -> bool:
        ...
    async def connect(self):
        ...
    async def fetch_status(self):
        if not self.is_connected():
            raise RuntimeError("Not connected")
        response = await self._http_client.get("/rest/system/status")
        response.raise_for_status()
        status = response.json()
        self.my_device_id = status.get("myID")

@dataclass
class SSHSyncThingConnection(SyncThingConnection):
    connection_string: str

    _ssh_client: asyncssh.SSHClientConnection|None = field(init=False, default=None)
    _ssh_http_port_listener: asyncssh.SSHListener|None = field(init=False, default=None)
    _is_connected: bool = field(init=False, default=False)

    def is_connected(self) -> bool:
        return self._is_connected

    async def connect(self):
        try:
            if self.is_connected():
                raise RuntimeError("Already connected")
            self._ssh_client = await asyncssh.connect(
                self.connection_string,
            )
            config_response = await self._ssh_client.run(f"{self.syncthing_binary_path} cli config dump-json", check=True)
            config_json = json.loads(config_response.stdout) # type: ignore
            if not config_json.get("gui", {}).get("enabled", False):
                raise RuntimeError("Syncthing GUI is not enabled on the remote device")
            api_key = config_json.get("gui", {}).get("apiKey", "")
            address = config_json.get("gui", {}).get("address", "")
            remote_st_host, remote_st_port = address.rsplit(":", 1)

            self._ssh_http_port_listener = await self._ssh_client.forward_local_port(
                "localhost", 0, remote_st_host, int(remote_st_port)
            )
            self._http_client = httpx.AsyncClient(
                base_url=f"http://localhost:{self._ssh_http_port_listener.get_port()}",
                headers={"X-API-Key": api_key},
            )

            self._is_connected = True

            # Fetch the status to verify the connection and get the device ID
            await self.fetch_status()


        except Exception as e:
            msg = f"{self.connection_string}: Couldn't connect: {e!s}"
            raise RuntimeError(msg) from e


@app.command
def watch():
    print("Watching for changes...")

@app.command
def cp():
    print("Hello from Cyclopts")
