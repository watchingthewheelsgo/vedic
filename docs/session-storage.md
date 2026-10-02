# Session file storage

## Current default: local

`SESSION_STORAGE_BACKEND=local` is the default in Settings and both example environment files. In this mode the application does not construct an AWS client, discover AWS credentials, upload, or download anything. Existing files remain under `backend/data/sessions`, mounted from `/home/ubuntu/signatlas-data/sessions` on the VPS. This change does not migrate files or change a running deployment.

PostgreSQL continues to own users, authorization, journals, memberships, AI usage and the session index. S3 does not replace or back up PostgreSQL in this implementation.

## Prepared S3 mode (disabled)

```dotenv
SESSION_STORAGE_BACKEND=local
SESSION_S3_BUCKET=signatlas-user-data-180680162496
SESSION_S3_REGION=us-west-2
SESSION_S3_PREFIX=sessions
SESSION_S3_EXPECTED_OWNER=180680162496
```

Only change the first setting to `s3` when intentionally enabling uploads. Provide runtime credentials through the standard AWS SDK credential chain; never use frontend environment variables. Use a dedicated principal limited to `s3:GetObject` and `s3:PutObject` on this bucket's `sessions/*` prefix, plus `s3:AbortMultipartUpload` for cleanup of failed multipart uploads. The developer laptop profile is not automatically available inside the VPS container. The existing `tapvox-prod` profile was subsequently installed on the VPS at `/home/ubuntu/signatlas-secrets/aws-credentials` (directory 0700, file 0600, UID 1000). No IAM policy was changed. The backend mounts this directory read-only at `/run/signatlas-aws` and uses `AWS_SHARED_CREDENTIALS_FILE=/run/signatlas-aws/aws-credentials`, `AWS_PROFILE=tapvox-prod`, and `AWS_DEFAULT_REGION=us-west-2`. S3 remains disabled. The local `compose.vps.yml` now preserves this mount for future releases; `SIGNATLAS_AWS_CREDENTIALS_DIR` can override the host directory. The current deployed image uses `.deploy/aws-credentials.compose.yml` as an extra Compose file; include that override when recreating the old release until the updated base Compose file has shipped. That temporary override explicitly forces local storage and must be removed when intentionally enabling S3.

The agent still executes on the local filesystem. At a non-running session metadata synchronization, the application uploads a ZIP snapshot to `sessions/<session-id>/workspace.zip`. This includes recognized report/chart artifacts, public projections' source data, session/checkpoint metadata and exports; it excludes arbitrary files, generated tool environments and runtime caches. Existing S3 bucket versioning keeps previous snapshots. No public URLs or ACL grants are created. The same authenticated, ownership-checked API serves reports and downloads.

If the entire local session directory is missing, S3 mode restores its snapshot into a staging directory, verifies SHA-256 and archive boundaries, then publishes the directory. Existing local directories are not overwritten or automatically evicted. This is single-writer S3 persistence with a local working copy, not a distributed filesystem or a multi-replica synchronization protocol. Do not run multiple independent writers against the same session prefix.

Archive upload errors surface to the caller, preserving local files and the previous remote object. An interrupted rectification transaction cannot be archived. Requests during running jobs skip archival; crash recovery relies on local persistent storage until a completed snapshot is uploaded. Snapshots are limited to 512 MiB uncompressed and 10,000 files. Local metadata still points to the local working copy. Generated PDFs are included on the export route's metadata synchronization.

## Future rollout and rollback

1. Back up PostgreSQL and the local session directory. Pause writes before migration or recovery.
2. Configure a scoped backend AWS principal; validate bucket owner, encryption, public-access block and versioning.
3. Set `SESSION_STORAGE_BACKEND=s3` and recreate the backend with its current image/configuration. Startup's existing session backfill will archive local non-running sessions, including existing user content: enable only when this data transfer is intended. A failure can prevent startup, with local files retained for rollback.
4. Verify an authorized report read/export and recovery of a synthetic session from S3 before considering local cleanup. No real S3 roundtrip was performed in this implementation task because S3 must stay disabled.
5. To return to `local`, first ensure every required session exists locally (restore remote-only sessions while S3 mode is active), then switch to `local` and recreate the backend. Do not delete database ownership records.

For a fully lost VPS, restore the database backup first, recreate runtime configuration and enable S3 mode. The database session index identifies the sessions; local directories are fetched on demand. S3 snapshots are not a complete database/disaster-recovery backup.

SDK reference: https://docs.aws.amazon.com/boto3/latest/guide/s3.html
