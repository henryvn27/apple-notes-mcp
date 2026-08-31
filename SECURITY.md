# Security

## Boundary

Apple Notes MCP exposes four discovery/read tools and seven single-object
mutation tools. Reads can list account and folder metadata, search note titles
and plaintext, and return the full contents and attachment metadata for one
exact note. Mutations create or rename one folder, or create, append to,
rename, move, replace, or delete one exact note.

Shared folders and shared or password-protected notes are read-only. Content
replacement is also blocked when a note has attachments because replacing the
HTML body could remove them. The server exposes no bulk delete, folder delete,
attachment writer, account mutation, or password operation. Deletes and body
replacement are marked destructive; create and delete operations are marked
non-idempotent.

The server invokes a fixed JXA file through `/usr/bin/osascript`. User input is
serialized as JSON and passed as a separate process argument. It is never
interpolated into shell commands or executable source. Plaintext writes are
HTML-escaped by the fixed bridge. Inputs reject unknown fields, null bytes,
oversized values, invalid date-times, ambiguous selectors, and exact-target
mutations without native IDs.

## Data access

Searches can return note titles, plaintext previews, account and folder names,
native IDs, timestamps, sharing and lock status, and attachment counts. Reading
one exact note can additionally return its plaintext, HTML body, and attachment
metadata. Attachment contents are never returned.

Local Codex use requires no API key and sends nothing to this project. macOS
Automation permission and Notes data remain on the Mac unless the calling MCP
client or a user-configured tunnel transmits returned data. When a remote MCP
tunnel is used, that tunnel and client are part of the data boundary.

## Reporting a vulnerability

Use [GitHub private vulnerability reporting](https://github.com/henryvn27/apple-notes-mcp/security/advisories/new).
Include the affected version, reproduction steps, and expected impact. Do not
open a public issue for an unpatched vulnerability.

## Credentials

The plugin requires no credentials for local Codex use. Keep credentials for
any optional remote MCP tunnel outside this repository.
