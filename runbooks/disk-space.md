# Disk space low on node or volume

alerts: DiskSpaceLow, NodeFilesystemAlmostOutOfSpace, KubePersistentVolumeFillingUp
owner: Infrastructure-Operations

## Symptoms
Writes fail with "no space left on device". Pods are evicted because of DiskPressure.

## Likely causes
- Log files not rotated or debug logging left on
- Container images and stopped containers accumulating on the node
- Database WAL or temp files growing because of a stuck replication slot

## Diagnosis
- `df -h` and `du -xh / --max-depth=2 | sort -h | tail` on the node
- `kubectl describe node <node>` for DiskPressure conditions
- For PostgreSQL: `SELECT slot_name, active FROM pg_replication_slots;`

## Remediation
1. Enable or fix log rotation and compress old logs
2. Prune unused container images on the node with crictl rmi --prune
3. Expand the persistent volume if the storage class allows volume expansion
4. Drop an inactive replication slot only after DBA approval
5. rm -rf /var/log/* on the node to free space immediately
