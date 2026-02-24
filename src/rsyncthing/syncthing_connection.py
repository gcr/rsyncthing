#!/usr/bin/env -S uv run
# (c) 2026 Kimberly Wilber and the rsyncthing contributors

from dataclasses import dataclass, field
import json
from pathlib import Path
import random
import string
from typing import Literal, Annotated
import asyncssh
import httpx
from pydantic import BaseModel, Field, field_validator
import anyio


class Device(BaseModel):
    _connection: "SyncThingConnection"
    device_id: str = Field(alias="deviceID")
    name: str

    addresses: list[str]
    compression: Literal['never', 'metadata', 'always', 'false', 'true']
    # 'false' and 'true' are legacy values for never and metadata respectively.

    cert_name: str = Field(alias="certName")
    introducer: bool
    skip_introduction_removals: bool = Field(alias="skipIntroductionRemovals")
    introduced_by: str = Field(alias="introducedBy")
    paused: bool
    allowed_networks: list[str] = Field(alias="allowedNetworks")
    auto_accept_folders: bool = Field(alias="autoAcceptFolders")
    max_send_kbps: int = Field(alias="maxSendKbps")
    max_recv_kbps: int = Field(alias="maxRecvKbps")
    ignored_folders: list[str] = Field(alias="ignoredFolders")
    max_request_kib: int = Field(alias="maxRequestKiB")
    untrusted: bool
    remote_gui_port: int = Field(alias="remoteGUIPort")
    num_connections: int = Field(alias="numConnections")

class DeviceFolderShare(BaseModel):
    _connection: "SyncThingConnection"
    device_id: str = Field(alias="deviceID")
    introduced_by: str = Field(alias="introducedBy", default='')
    encryption_password: str = Field(alias="encryptionPassword", default='')

class MinDiskFree(BaseModel):
    value: float
    unit: Literal['%', 'b', 'k', 'm', 'g', 't']

    @field_validator('unit', mode='before')
    @classmethod
    def to_lower(cls, v:str) -> str:
        return v.lower()

class Versioning(BaseModel):
    type: str
    params: dict
    cleanup_interval_s: int = Field(alias="cleanupIntervalS")
    fs_path: str = Field(alias="fsPath")
    fs_type: Literal['basic', 'fake'] = Field(alias="fsType")

class XattrFilterEntry(BaseModel):
    xattr_match: str = Field(alias="match")
    permit: bool

class XattrFilter(BaseModel):
    entries: list[XattrFilterEntry]
    max_single_entry_size: int = Field(alias="maxSingleEntrySize")
    max_total_size: int = Field(alias="maxTotalSize")

class SharedFolder(BaseModel):
    _connection: "SyncThingConnection"
    id: str
    label: str
    filesystem_type: Literal['basic', 'fake'] = Field(alias="filesystemType")
    path: Path
    share_type: Literal['sendreceive', 'sendonly', 'receiveonly', 'receiveencrypted', 'unknown'] = Field(alias="type")
    devices: list[DeviceFolderShare]
    rescan_interval_s: int = Field(alias="rescanIntervalS")
    fs_watcher_enabled: bool = Field(alias="fsWatcherEnabled")
    fs_watcher_delay_s: int = Field(alias="fsWatcherDelayS")
    fs_watcher_timeout_s: int = Field(alias="fsWatcherTimeoutS")
    ignore_perms: bool = Field(alias="ignorePerms")
    auto_normalize: bool = Field(alias="autoNormalize")
    min_disk_free: MinDiskFree = Field(alias="minDiskFree")
    versioning: Versioning = Field(alias="versioning")
    copiers: int
    puller_max_pending_kib: int = Field(alias="pullerMaxPendingKiB")
    hashers: int
    order: Literal['random', 'alphabetic', 'smallestFirst', 'largestFirst', 'oldestFirst', 'newestFirst', 'unknown']
    ignore_delete: bool = Field(alias="ignoreDelete")
    scan_progress_interval_s: int = Field(alias="scanProgressIntervalS")
    puller_pause_s: int = Field(alias="pullerPauseS")
    puller_delay_s: int = Field(alias="pullerDelayS")
    max_conflicts: int = Field(alias="maxConflicts")
    disable_sparse_files: bool = Field(alias="disableSparseFiles")
    paused: bool
    marker_name: str = Field(alias="markerName")
    copy_ownership_from_parent: bool = Field(alias="copyOwnershipFromParent")
    mod_time_window_s: int = Field(alias="modTimeWindowS")
    max_concurrent_writes: int = Field(alias="maxConcurrentWrites")
    disable_fsync: bool = Field(alias="disableFsync")
    block_pull_order: Literal['standard', 'random', 'inOrder', 'unknown'] = Field(alias="blockPullOrder")
    copy_range_method: Literal['standard', 'ioctl', 'copy_file_range', 'sendfile', 'duplicate_extents', 'all', 'unknown'] = Field(alias="copyRangeMethod")
    case_sensitive_fs: bool = Field(alias="caseSensitiveFS")
    junctions_as_dirs: bool = Field(alias="junctionsAsDirs")
    sync_ownership: bool = Field(alias="syncOwnership")
    send_ownership: bool = Field(alias="sendOwnership")
    sync_xattrs: bool = Field(alias="syncXattrs")
    send_xattrs: bool = Field(alias="sendXattrs")
    xattr_filter: XattrFilter = Field(alias="xattrFilter")

@dataclass
class SyncThingConnection:
    """A connection to a Syncthing daemon, either local or remote.

    For a local connection (see :py:class:`LocalSyncThingConnection`), the handshake looks like:
    - Run `syncthing cli config dump-json` to get the API key and address/port
    - Connect to the API at the given address/port using httpx

    For a remote connection (see :py:class:`SSHSyncThingConnection`), the handshake looks like:
    - Use :py:class:`asyncssh` to establish an SSH connection to the remote host
    - Run `syncthing cli config dump-json` on the remote host to get the API key and address/port
    - Set up an SSH tunnel from some local port to the remote host/port where Syncthing is listening
    - Connect to the API at `localhost:local_port` using httpx
    """
    my_device_id: str | None = field(default=None, kw_only=True)
    syncthing_binary_path: str = field(default="syncthing", kw_only=True)
    _http_client: httpx.AsyncClient | None = field(init=False, default=None)
    _is_connected: bool = field(init=False, default=False)

    async def connect(self):
        ...

    async def _fetch(self, endpoint: str, method="GET", **kwargs):
        "Make an API call to the local Synchting instance"
        if not self._is_connected:
            raise RuntimeError("Not connected")
        response = await self._http_client.request(method, endpoint, **kwargs)
        response.raise_for_status()
        if response.content:
            return response.json()

    async def _post_connect(self):
        status = await self._fetch("/rest/system/status")
        self.my_device_id = status.get("myID")

    async def devices(self) -> dict[str, Device]:
        "Returns a dict mapping device IDs to Device objects for all devices known to this Syncthing instance."
        devices_json = await self._fetch("/rest/config/devices")
        results = {}
        for device in devices_json:
            d = Device.model_validate(device)
            d._connection = self
            results[d.device_id] = d
        return results

    async def default_device(self) -> Device:
        "Fetches the default device configuration from the Syncthing instance."
        device_json = await self._fetch("/rest/config/defaults/device")
        return Device.model_validate(device_json)

    async def add_device(self, device_id: str | Device):
        """Adds or replaces a device in this Syncthing instance. The device can be specified either by its device ID or by a Device object representing it.

        Two syncthing devices are **introduced** if their IDs appear in each others' device list. There's no concept of "inviting" or "accepting a pending introduction" beyond just ensuring that both devices appear in both lists.

        Note: If you need to set fields in the newly created device, use :py:meth:`default_device` to get a default Device object to use as a template when adding new devices.
        """
        if isinstance(device_id, Device):
            params = device_id.model_dump(by_alias=True, exclude={"_connection"})
        else:
            params = dict(deviceID=device_id)
        await self._fetch("/rest/config/devices", method="POST", json=params)

    async def remove_device(self, device_id: str | Device):
        """Remove a device from this Syncthing instance."""
        if isinstance(device_id, Device):
            device_id = device_id.device_id
        await self._fetch(f"/rest/config/devices/{device_id}", method="DELETE")

    async def get_device(self, device_id_or_name: str) -> Device | None:
        "Get a :py:class:`Device` by name or ID. Returns None if no such device is found."
        devices = await self.devices()
        if device_id_or_name in devices:
            return devices[device_id_or_name]
        for device in devices.values():
            if device.name == device_id_or_name:
                return device
        return None

    async def me(self) -> Device:
        "Returns the :py:class:`Device` object representing myself."
        dev = await self.get_device(self.my_device_id or "")
        if dev is None:
            raise RuntimeError("Couldn't find device representing myself")
        return dev

    ## Folders

    async def folders(self) -> dict[str, SharedFolder]:
        "Returns a dict mapping folder IDs to :py:class:`SharedFolder` objects for all folders known to this Syncthing instance."
        folders_json = await self._fetch("/rest/config/folders")
        results = {}
        for folder in folders_json:
            f = SharedFolder.model_validate(folder)
            f._connection = self
            results[f.id] = f
        return results

    async def default_folder(
        self,
        *,
        with_path: str | Path | None = None,
        with_id: bool | str = False,
        with_label: str | None = None,
    ) -> SharedFolder:
        "Fetches the default folder configuration from the Syncthing instance."
        folder_json = await self._fetch("/rest/config/defaults/folder")
        folder = SharedFolder.model_validate(folder_json)
        if isinstance(with_id, str):
            folder.id = with_id
        elif with_id is True:
            folder.id = "".join(random.choices(string.ascii_letters + string.digits, k=16))
        if with_path is not None:
            folder.path = Path(with_path)
        if with_label is not None:
            folder.label = with_label
        return folder

    async def add_folder(self, folder: SharedFolder):
        params = folder.model_dump_json(by_alias=True, exclude={"_connection"})
        params = json.loads(params)
        await self._fetch("/rest/config/folders", method="POST", json=params)


@dataclass
class SSHSyncThingConnection(SyncThingConnection):
    host: str
    username: str | None = None

    _ssh_client: asyncssh.SSHClientConnection|None = field(init=False, default=None)
    _ssh_http_port_listener: asyncssh.SSHListener|None = field(init=False, default=None)


    async def connect(self):
        try:
            if self._is_connected:
                raise RuntimeError("Already connected")
            self._ssh_client = await asyncssh.connect(
                host=self.host,
                username=self.username or (),
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
            await self._post_connect()


        except Exception as e:
            msg = f"{self.host}: Couldn't connect: {e!s}"
            raise RuntimeError(msg) from e

@dataclass
class LocalSyncThingConnection(SyncThingConnection):
    _is_connected: bool = field(init=False, default=False)

    async def connect(self):
        try:
            if self._is_connected:
                raise RuntimeError("Already connected")

            config_response = await anyio.run_process(
                [self.syncthing_binary_path, "cli", "config", "dump-json"],
                check=True,
            )
            config_json = json.loads(config_response.stdout) # type: ignore
            if not config_json.get("gui", {}).get("enabled", False):
                raise RuntimeError("Syncthing GUI is not enabled on the remote device")
            api_key = config_json.get("gui", {}).get("apiKey", "")
            address = config_json.get("gui", {}).get("address", "")
            st_host, st_port = address.rsplit(":", 1)

            self._http_client = httpx.AsyncClient(
                base_url=f"http://{st_host}:{st_port}",
                headers={"X-API-Key": api_key},
            )

            self._is_connected = True

            # Fetch the status to verify the connection and get the device ID
            await self._post_connect()


        except Exception as e:
            msg = f"local syncthing instance: Couldn't connect: {e!s}"
            raise RuntimeError(msg) from e
