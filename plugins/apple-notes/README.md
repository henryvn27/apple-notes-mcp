# Apple Notes

A zero-dependency MCP server for reading and safely managing the native macOS
Notes app.

## Tools

| Tool | Effect |
| --- | --- |
| `list_note_folders` | Read account and folder names, native IDs, hierarchy, sharing, and counts |
| `create_note_folder` | Create one top-level folder in an explicit or default account |
| `rename_note_folder` | Rename one exact non-shared folder |
| `search_notes` | Search and paginate note titles and plaintext previews |
| `get_note` | Read one note and its HTML, plaintext, metadata, and attachment metadata |
| `add_note` | Create one plaintext note in an explicit or default folder |
| `append_to_note` | Append escaped plaintext while preserving existing rich content |
| `rename_note` | Rename one exact note without replacing its body |
| `move_note` | Move one exact note to one exact non-shared folder |
| `replace_note_content` | Replace one exact attachment-free note with escaped plaintext |
| `delete_note` | Move one exact note to Recently Deleted |

Shared and password-protected notes are read-only. Replacement is blocked when
a note contains attachments. The server exposes no bulk delete, folder delete,
attachment writer, account mutation, or password operation.

## Verify

```bash
cd plugins/apple-notes
/usr/bin/python3 -m unittest discover -s tests -v
python3 -m py_compile server.py
osacompile -l JavaScript -o /tmp/apple-notes.scpt notes.js
```

Automated tests do not access Notes. The first live use may trigger a macOS
Automation permission prompt. Allow the calling app to control Notes. The
permission and Notes data remain on the Mac unless the calling client transmits
returned data.
