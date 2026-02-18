#!/usr/bin/env -S uv run
# (c) 2026 Kimberly Wilber and the rsyncthing contributors

from dataclasses import dataclass, field
import json
from pathlib import Path
import asyncssh
import httpx
from pydantic import BaseModel, Field
import anyio

class Device(BaseModel):
    _connection: "SyncThingConnection"
    device_id: str = Field(alias="deviceID")
    name: str
    addresses: list[str]
    compression: str
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
    introduced_by: str = Field(alias="introducedBy")
    encryption_password: str = Field(alias="encryptionPassword")

class MinDiskFree(BaseModel):
    value: int
    unit: str

class Versioning(BaseModel):
    type: str
    params: dict
    cleanup_interval_s: int = Field(alias="cleanupIntervalS")
    fs_path: str = Field(alias="fsPath")
    fs_type: str = Field(alias="fsType")

class SharedFolder(BaseModel):
    _connection: "SyncThingConnection"
    id: str
    label: str
    filesystem_type: str = Field(alias="filesystemType")
    path: Path
    share_type: str = Field(alias="type")
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
    order: str
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
    block_pull_order: str = Field(alias="blockPullOrder")
    copy_range_method: str = Field(alias="copyRangeMethod")
    case_sensitive_fs: bool = Field(alias="caseSensitiveFS")
    junctions_as_dirs: bool = Field(alias="junctionsAsDirs")
    sync_ownership: bool = Field(alias="syncOwnership")
    send_ownership: bool = Field(alias="sendOwnership")
    sync_xattrs: bool = Field(alias="syncXattrs")
    send_xattrs: bool = Field(alias="sendXattrs")
    xattr_filter: dict = Field(alias="xattrFilter")

@dataclass
class SyncThingConnection:
    my_device_id: str | None = field(default=None, kw_only=True)
    syncthing_binary_path: str = field(default="syncthing", kw_only=True)
    _http_client: httpx.AsyncClient | None = field(init=False, default=None)
    _is_connected: bool = field(init=False, default=False)

    async def connect(self):
        ...

    async def devices(self) -> dict[str, Device]:
        devices_json = await self._fetch("/rest/config/devices")
        results = {}
        for device in devices_json:
            d = Device.model_validate(device)
            d._connection = self
            results[d.device_id] = d
        return results

    async def me(self) -> Device:
        if not self.my_device_id:
            raise RuntimeError("Device ID not set. Have you called connect()?")
        return (await self.devices())[self.my_device_id]

    async def folders(self) -> dict[str, SharedFolder]:
        folders_json = await self._fetch("/rest/config/folders")
        results = {}
        for folder in folders_json:
            f = SharedFolder.model_validate(folder)
            f._connection = self
            results[f.id] = f
        return results

    async def _fetch(self, endpoint: str, method="GET", **kwargs):
        if not self._is_connected:
            raise RuntimeError("Not connected")
        response = await self._http_client.request(method, endpoint, **kwargs)
        response.raise_for_status()
        if response.content:
            return response.json()

    async def fetch_status(self):
        status = await self._fetch("/rest/system/status")
        self.my_device_id = status.get("myID")

    async def add_device(self, device_id: str | Device):
        if isinstance(device_id, Device):
            params = device_id.model_dump(by_alias=True, exclude={"_connection"})
        else:
            params = dict(deviceID=device_id)
        await self._fetch("/rest/config/devices", method="POST", json=params)
    async def remove_device(self, device_id: str | Device):
        if isinstance(device_id, Device):
            device_id = device_id.device_id
        await self._fetch(f"/rest/config/devices/{device_id}", method="DELETE")
    async def has_device(self, device_id_or_name: str) -> bool:
        devices = await self.devices()
        return any(
            d.device_id == device_id_or_name or d.name == device_id_or_name
            for d in devices.values()
        )

@dataclass
class SSHSyncThingConnection(SyncThingConnection):
    connection_string: str

    _ssh_client: asyncssh.SSHClientConnection|None = field(init=False, default=None)
    _ssh_http_port_listener: asyncssh.SSHListener|None = field(init=False, default=None)


    async def connect(self):
        try:
            if self._is_connected:
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
            await self.fetch_status()


        except Exception as e:
            msg = f"local syncthing instance: Couldn't connect: {e!s}"
            raise RuntimeError(msg) from e
