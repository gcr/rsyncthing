# rsyncthing: A CLI for syncthing that's as easy to use as rsync.

If you can ssh to a remote server, you can connect to its syncthing daemon.

# WARNING: work in progress! nothing works yet! placeholder package!

## Quickstart

### Share a local folder to remote hosts
```shell
rsyncthing cp /path/to/src hobbes:abc/
```
This command will:
1. Log into the local syncthing daemon
2. Log into `hobbes`' syncthing daemon using SSH tunnels
3. Ensure both devices are introduced
4. Share `/path/to/src` to `hobbes`
4. Remotely accept the invitation on `hobbes`
5. Show progress while the folder sync completes
6. Exit

### Sharing to many remotes
```shell
rsyncthing cp /path/to/src remote1:abc/ remote2:def/ remote3:ghi
```
This command will:
1. Log into the local syncthing daemon
2. Log into `remote1`'s syncthing daemon over SSH
2. Log into `remote2`'s syncthing daemon over SSH
2. Log into `remote3`'s syncthing daemon over SSH
3. Ensure all devices are introduced
4. Share `/path/to/src` to `remote1`, `remote2`, and `remote3`
4. Remotely accept the invitation on each device
5. Show progress while the folder sync completes
6. Exit

# notes
- Need to ensure that the source device isn't marked as 'automatically accept' for any of the target devices