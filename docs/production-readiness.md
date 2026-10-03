# Private media, recovery and backup operations

ParkinSense now has executable controls for these workflows. A clinic deployment still needs an operator, HTTPS, network configuration, an approved retention policy and a recorded restore drill. Local tests do not demonstrate that those operational arrangements are in place.

## Authorized recording and export access

`backend/production.py` issues opaque, random media capabilities. A capability contains no patient name, assessment ID or storage path. Only its SHA-256 hash is stored. The default lifetime is 180 seconds, with a maximum of 600 seconds. Issuance checks the authenticated actor, assessment access and current consent. Requests repeat those checks, including the current clinician link, active account, password session revision, expiry and revocation. An in-progress stream repeats authorization every 256 KB.

Issuance also locks the patient-owner row, including when the requester is a linked clinician, so concurrent consent withdrawal revokes any grant issued before it completes. Renewing consent does not revive these revoked URLs. PostgreSQL tests cover both the race and the exact patient-owner lock.

Start the gateway separately from Streamlit:

```sh
.venv/bin/python scripts/secure_media_server.py
```

It binds to `127.0.0.1:8503`, provides `/health`, and never serves a directory or accepts a filesystem path. It supports GET, HEAD and a single byte range; range responses are capped at 8 MB and full responses stream in bounded chunks. Responses use `private, no-store`, `nosniff`, a restrictive content security policy and `no-referrer`. Generated reports are attachments with validated filenames. Application and gateway access logs must not retain capability URLs. Reverse proxy access logging for `/media/` must also be disabled or redact the entire path.

Interactive HTML exports are delivered as attachments with scripts restricted while served by the gateway. Save the downloaded file locally to replay an exported 3D scene. The protected endpoint does not host patient HTML as executable application content.

`PARKINSENSE_MEDIA_BASE_URL` is a trusted operator setting. Its default is `http://127.0.0.1:8503`. For a remote clinic, use a same-site HTTPS media origin such as `https://media.clinic.example` and proxy `/media/` to the loopback gateway. A phone cannot reach the server through the phone's own `127.0.0.1`. Public HTTP origins, embedded credentials, query strings and base paths are rejected. TLS configuration belongs to the clinic's reverse proxy; the gateway is deliberately loopback only.

Integration contracts:

- `create_media_grant(actor_id, assessment_id, file_id, session_key=..., expected_revision=...)` returns `url` and `expires_at`.
- `create_artifact_grant(actor_id, assessment_id, data, filename, mime_type, session_key=..., expected_revision=...)` privately stores an export of at most 10 MB and returns the same fields.
- `revoke_media_grants(actor_id, session_key=...)` revokes that browser session's capabilities on logout.
- Cache an issued player URL until shortly before expiry. Refreshing the same file in the same session replaces the earlier capability.

The session key must be generated on the server, never accepted from a submitted form. Pass the revision captured at login to issuance. Revocation stops future authorized delivery; it cannot erase bytes a user has already downloaded or captured. No claim of DRM is made.

Expired generated exports can be removed with this local operator command. It retains source recordings:

```sh
.venv/bin/python scripts/secure_media_server.py --prune-expired
```

These choices follow OWASP's requirement to verify resource authorization for each request and deny access when it is not granted. [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html).

## Administrator-verified account recovery

There is no public code-issuance endpoint or automatic email provider. The clinic must verify the owner using its established support procedure and private delivery channel. Knowing a patient name or email is not identity verification.

Create a private directory once, then issue a code interactively:

```sh
mkdir -m 700 /private/operator-recovery
.venv/bin/python scripts/account_recovery.py --user-id VERIFIED_ACCOUNT_UUID --identity-verified --output /private/operator-recovery/recovery-code.txt
```

The CLI authenticates an active administrator with an interactive password prompt. It writes the code into a new file with permission 600; it does not print it into terminal logs. The code expires after 20 minutes, works once, and exists in the database only as a hash. A new issuance revokes the earlier code. Issuance is limited to three per account per 30 minutes; redemption records persistent token/client-bucket limits. A deployment must add IP-based throttling at its reverse proxy because browser session buckets alone cannot prevent distributed abuse.

The verified owner redeems the code with a new password in the app. Successful redemption changes the password hash, revokes outstanding codes and media capabilities, and increments the account session revision. Successful sign-in captures the revision in the same locked transaction as the password check; session initialization verifies that captured revision, so a reset between authentication and session initialization cannot upgrade a stale login into a valid new session. The app checks the revision on each rerun and requires normal sign-in afterwards. It does not automatically log the user in. Inactive, expired, revoked and replayed codes use the same failure message. Delete the private delivery file after use. Notification delivery and MFA remain deployment work; this project does not claim they are configured.

Token generation, expiry, single use, secure storage and session invalidation follow the [OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html).

## Encrypted snapshots and non-destructive restore drills

The backup contains every database table plus all regular files under `PARKINSENSE_STORAGE_ROOT`, including recordings and temporary generated exports. It excludes `.env`, application secrets and model files outside that root. It uses a single database snapshot (repeatable read on PostgreSQL), streams logical rows, and includes a file inventory, SHA-256 checksums and per-table counts. Each column value has an explicit wrapper, so JSON containing fields such as `$type` is preserved as patient JSON rather than misinterpreted as a date.

Database and filesystem writes must be paused for the maintenance window. The command requires an explicit `--writes-paused` attestation; it does not silently stop the running clinic or assert that writes are paused. Finish uploads/recordings, stop Streamlit and the gateway, create the snapshot, and then resume the services. An unfinished upload, symlink or changing media file causes failure.

```sh
mkdir -m 700 /private/parkinsense-backups
.venv/bin/python scripts/backup_private.py --writes-paused --output /private/parkinsense-backups/snapshot-2026-10-03.pspk
.venv/bin/python scripts/restore_drill.py --input /private/parkinsense-backups/snapshot-2026-10-03.pspk --output-directory /private/parkinsense-backups/drill-2026-10-03
```

The passphrase is entered interactively, with at least 16 characters. It never appears in a command line or log. AES-256-GCM authenticates the complete archive and header, with a separate scrypt-derived key and fresh salt/nonce per snapshot. Keep the passphrase separately from the backup, under the clinic's recovery procedure. Full-disk encryption is still needed for source data and the private temporary files used during snapshots and drills.

Restore drills authenticate the archive before reading it, reject traversal, links, duplicates and excessive expansion, verify every checksum, and restore all rows into a **new isolated SQLite database**. The drill compares row counts and writes `restore-verification.json`. It never points a restored database at the production configuration or overwrites an existing directory. Use the same application/schema version as the snapshot. The isolated drill contains private health data; keep its directory at permission 700 and remove it after review.

This is a recoverability test, not an automatic production failover. A production PostgreSQL restoration requires a separately reviewed maintenance procedure, service/account reconfiguration, validation of application access and an approved switch-over. Revoke restored media/recovery capabilities and invalidate sessions before exposing a restored service; an older snapshot may predate a password change or consent withdrawal, which must be reconciled from the clinic's current records. Keep encrypted copies off the application machine, choose backup frequency/retention with the clinic, and record actual restore duration and who verified the result. No schedule, off-site destination or encryption key custody is automatically configured.

## Data handling and remaining deployment work

The private dataset contains identities, consent records, recordings, world landmarks, derived measurements, self-reports, reports, clinician notes and sanitized audit events. UUID paths reduce accidental disclosure of names; they do not anonymize the linked clinical records. Local extraction does not send patient media to an external AI service by default. If cloud models or STUN/TURN services are enabled, describe the actual processors, destinations and network metadata in the clinic's patient information before use.

Assign a named data controller and support contact. Publish the purposes of collection, who may review recordings, storage location, retention periods, consent withdrawal and the process for access/correction/deletion requests. Distinguish access revocation from retention/deletion: withdrawing monitoring consent must immediately deny subsequent media delivery, while any legal retention decision requires the clinic's approved policy. Apply that decision to encrypted backups and completed drill directories as well as the live database.

Before exposing the app beyond the local workstation, configure HTTPS and a same-site media origin, trusted WebRTC networking, persistent authentication throttling, least-privilege PostgreSQL credentials, encrypted disks, secret rotation, restricted operator access, monitoring without patient payloads, a dependency update process and a tested recovery runbook. The included code supplies controls that can be tested; it does not certify compliance, medical efficacy or a deployed production service.

## Verification

`tests/test_production_security.py` covers opaque hashed grants, patient/clinician scoping, link/consent/account changes, expiry, session revocation, protected report attachments, persistent recovery limits, replay/expiry/inactive recovery, password-session invalidation, real loopback HTTP range/HEAD/security headers, encrypted DB/media round trips, authentication tampering and unsafe archive members. Fixtures use isolated synthetic accounts and media only.
