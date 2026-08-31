#!/usr/bin/env python3
"""Dependency-free MCP server for native Apple Notes."""

import datetime as dt
import json
import subprocess
import sys
from pathlib import Path


PROTOCOL_VERSION = "2025-06-18"
SERVER_VERSION = "0.1.0"
BRIDGE = Path(__file__).with_name("notes.js")


def _annotations(title, *, read_only, destructive=False, idempotent=True):
    return {
        "title": title,
        "readOnlyHint": read_only,
        "destructiveHint": destructive,
        "idempotentHint": idempotent,
        "openWorldHint": False,
    }


NOTE_ID_SCHEMA = {
    "type": "string",
    "minLength": 1,
    "maxLength": 1024,
    "description": "Exact native note ID returned by a read tool.",
}
FOLDER_ID_SCHEMA = {
    "type": "string",
    "minLength": 1,
    "maxLength": 1024,
    "description": "Exact native folder ID returned by list_note_folders.",
}
ACCOUNT_ID_SCHEMA = {
    "type": "string",
    "minLength": 1,
    "maxLength": 1024,
    "description": "Exact native account ID returned by list_note_folders.",
}
FOLDER_SCHEMA = {
    "type": "string",
    "minLength": 1,
    "maxLength": 256,
    "description": "Exact Notes folder name. Duplicate names are rejected.",
}
ACCOUNT_SCHEMA = {
    "type": "string",
    "minLength": 1,
    "maxLength": 256,
    "description": "Exact Notes account name. Duplicate names are rejected.",
}
DATE_TIME_SCHEMA = {
    "type": "string",
    "description": (
        "ISO 8601 date-time with an explicit UTC offset, such as "
        "2026-09-01T16:00:00-04:00."
    ),
}
TITLE_SCHEMA = {"type": "string", "minLength": 1, "maxLength": 512}
BODY_SCHEMA = {
    "type": "string",
    "maxLength": 100000,
    "description": "Plaintext. The fixed bridge HTML-escapes it before writing.",
}


TOOLS = [
    {
        "name": "list_note_folders",
        "title": "List Apple Notes Folders",
        "description": (
            "List native Notes accounts and folders with exact IDs, hierarchy, "
            "sharing state, defaults, and note counts."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        "annotations": _annotations("List Apple Notes Folders", read_only=True),
    },
    {
        "name": "create_note_folder",
        "title": "Create Apple Notes Folder",
        "description": (
            "Create one top-level folder in the default account or one explicitly "
            "selected account."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": FOLDER_SCHEMA,
                "account": ACCOUNT_SCHEMA,
                "account_id": ACCOUNT_ID_SCHEMA,
            },
            "required": ["name"],
            "additionalProperties": False,
        },
        "annotations": _annotations(
            "Create Apple Notes Folder", read_only=False, idempotent=False
        ),
    },
    {
        "name": "rename_note_folder",
        "title": "Rename Apple Notes Folder",
        "description": "Rename one non-shared folder by its exact native ID.",
        "inputSchema": {
            "type": "object",
            "properties": {"id": FOLDER_ID_SCHEMA, "name": FOLDER_SCHEMA},
            "required": ["id", "name"],
            "additionalProperties": False,
        },
        "annotations": _annotations("Rename Apple Notes Folder", read_only=False),
    },
    {
        "name": "search_notes",
        "title": "Search Apple Notes",
        "description": (
            "Search note titles and plaintext previews. Optionally select an account "
            "or folder, include nested folders, filter by modification time, and paginate."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "maxLength": 512,
                    "description": "Optional case-insensitive title or plaintext text.",
                },
                "account": ACCOUNT_SCHEMA,
                "account_id": ACCOUNT_ID_SCHEMA,
                "folder": FOLDER_SCHEMA,
                "folder_id": FOLDER_ID_SCHEMA,
                "include_subfolders": {"type": "boolean", "default": False},
                "modified_after": DATE_TIME_SCHEMA,
                "modified_before": DATE_TIME_SCHEMA,
                "offset": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 10000,
                    "default": 0,
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 100,
                    "default": 25,
                },
            },
            "additionalProperties": False,
        },
        "annotations": _annotations("Search Apple Notes", read_only=True),
    },
    {
        "name": "get_note",
        "title": "Get Apple Note",
        "description": (
            "Read one note by exact native ID, including plaintext, HTML, timestamps, "
            "folder identity, and attachment metadata."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"id": NOTE_ID_SCHEMA},
            "required": ["id"],
            "additionalProperties": False,
        },
        "annotations": _annotations("Get Apple Note", read_only=True),
    },
    {
        "name": "add_note",
        "title": "Add Apple Note",
        "description": (
            "Create one escaped-plaintext note in the default folder or an explicitly "
            "selected non-shared folder."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": TITLE_SCHEMA,
                "body": BODY_SCHEMA,
                "folder": FOLDER_SCHEMA,
                "folder_id": FOLDER_ID_SCHEMA,
            },
            "required": ["title"],
            "additionalProperties": False,
        },
        "annotations": _annotations(
            "Add Apple Note", read_only=False, idempotent=False
        ),
    },
    {
        "name": "append_to_note",
        "title": "Append to Apple Note",
        "description": (
            "Append escaped plaintext to one exact non-shared, unlocked note while "
            "preserving its existing rich content and attachments."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": NOTE_ID_SCHEMA,
                "text": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 50000,
                },
            },
            "required": ["id", "text"],
            "additionalProperties": False,
        },
        "annotations": _annotations(
            "Append to Apple Note", read_only=False, idempotent=False
        ),
    },
    {
        "name": "rename_note",
        "title": "Rename Apple Note",
        "description": "Rename one exact non-shared, unlocked note without replacing its body.",
        "inputSchema": {
            "type": "object",
            "properties": {"id": NOTE_ID_SCHEMA, "title": TITLE_SCHEMA},
            "required": ["id", "title"],
            "additionalProperties": False,
        },
        "annotations": _annotations("Rename Apple Note", read_only=False),
    },
    {
        "name": "move_note",
        "title": "Move Apple Note",
        "description": (
            "Move one exact non-shared, unlocked note to one exact non-shared folder."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"id": NOTE_ID_SCHEMA, "folder_id": FOLDER_ID_SCHEMA},
            "required": ["id", "folder_id"],
            "additionalProperties": False,
        },
        "annotations": _annotations("Move Apple Note", read_only=False),
    },
    {
        "name": "replace_note_content",
        "title": "Replace Apple Note Content",
        "description": (
            "Replace one exact attachment-free, non-shared, unlocked note with escaped "
            "plaintext. This discards existing formatting, so use append_to_note when possible."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": NOTE_ID_SCHEMA,
                "title": TITLE_SCHEMA,
                "body": BODY_SCHEMA,
            },
            "required": ["id", "body"],
            "additionalProperties": False,
        },
        "annotations": _annotations(
            "Replace Apple Note Content", read_only=False, destructive=True
        ),
    },
    {
        "name": "delete_note",
        "title": "Delete Apple Note",
        "description": (
            "Move one exact non-shared, unlocked note to Apple Notes’ Recently "
            "Deleted folder, where it can still be recovered or erased in Notes."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"id": NOTE_ID_SCHEMA},
            "required": ["id"],
            "additionalProperties": False,
        },
        "annotations": _annotations(
            "Delete Apple Note",
            read_only=False,
            destructive=True,
            idempotent=False,
        ),
    },
]
TOOL_NAMES = {tool["name"] for tool in TOOLS}


class UserError(Exception):
    pass


def _arguments(arguments, allowed):
    if not isinstance(arguments, dict):
        raise UserError("arguments must be an object")
    unknown = sorted(set(arguments) - allowed)
    if unknown:
        raise UserError(
            "unknown argument%s: %s"
            % ("" if len(unknown) == 1 else "s", ", ".join(unknown))
        )
    return arguments


def _text(
    value,
    field,
    maximum,
    *,
    required=False,
    allow_empty=False,
    preserve=False,
):
    if value is None and not required:
        return None
    if not isinstance(value, str):
        raise UserError("%s must be a string" % field)
    if "\x00" in value:
        raise UserError("%s cannot contain a null byte" % field)
    if len(value) > maximum:
        raise UserError("%s must be at most %d characters" % (field, maximum))
    result = value if preserve else value.strip()
    if required and not result.strip() and not allow_empty:
        raise UserError("%s cannot be empty" % field)
    return result if result or allow_empty else None


def _id(arguments, field="id"):
    return _text(arguments.get(field), field, 1024, required=True)


def _integer(arguments, field, minimum, maximum, default):
    value = arguments.get(field, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise UserError(
            "%s must be an integer from %d to %d" % (field, minimum, maximum)
        )
    if not minimum <= value <= maximum:
        raise UserError(
            "%s must be an integer from %d to %d" % (field, minimum, maximum)
        )
    return value


def _boolean(arguments, field, default=False):
    value = arguments.get(field, default)
    if not isinstance(value, bool):
        raise UserError("%s must be a boolean" % field)
    return value


def _date_time(value, field):
    value = _text(value, field, 64, required=True)
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise UserError("%s must be an ISO 8601 date-time" % field)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise UserError("%s must include an explicit UTC offset" % field)
    return parsed.isoformat(timespec="seconds")


def _selector(arguments, payload, name, id_name):
    if name in arguments and id_name in arguments:
        raise UserError("use either %s or %s, not both" % (name, id_name))
    if name in arguments:
        payload[name] = _text(arguments[name], name, 256, required=True)
    if id_name in arguments:
        payload[id_name] = _text(
            arguments[id_name], id_name, 1024, required=True
        )


def _content(arguments, field, maximum, *, required=False):
    if field not in arguments and not required:
        return None
    return _text(
        arguments.get(field),
        field,
        maximum,
        required=required,
        allow_empty=True,
        preserve=True,
    )


def normalize_arguments(name, arguments):
    if name == "list_note_folders":
        _arguments(arguments, set())
        return {"action": name}

    if name == "create_note_folder":
        arguments = _arguments(arguments, {"name", "account", "account_id"})
        payload = {
            "action": name,
            "name": _text(arguments.get("name"), "name", 256, required=True),
        }
        _selector(arguments, payload, "account", "account_id")
        return payload

    if name == "rename_note_folder":
        arguments = _arguments(arguments, {"id", "name"})
        return {
            "action": name,
            "id": _id(arguments),
            "name": _text(arguments.get("name"), "name", 256, required=True),
        }

    if name == "search_notes":
        arguments = _arguments(
            arguments,
            {
                "query",
                "account",
                "account_id",
                "folder",
                "folder_id",
                "include_subfolders",
                "modified_after",
                "modified_before",
                "offset",
                "limit",
            },
        )
        payload = {
            "action": name,
            "query": _text(arguments.get("query"), "query", 512),
            "include_subfolders": _boolean(
                arguments, "include_subfolders", default=False
            ),
            "offset": _integer(arguments, "offset", 0, 10000, 0),
            "limit": _integer(arguments, "limit", 1, 100, 25),
        }
        _selector(arguments, payload, "account", "account_id")
        _selector(arguments, payload, "folder", "folder_id")
        if "modified_after" in arguments:
            payload["modified_after"] = _date_time(
                arguments["modified_after"], "modified_after"
            )
        if "modified_before" in arguments:
            payload["modified_before"] = _date_time(
                arguments["modified_before"], "modified_before"
            )
        if payload.get("modified_after") and payload.get("modified_before"):
            if dt.datetime.fromisoformat(payload["modified_after"]) >= dt.datetime.fromisoformat(
                payload["modified_before"]
            ):
                raise UserError("modified_after must be before modified_before")
        return payload

    if name in {"get_note", "delete_note"}:
        arguments = _arguments(arguments, {"id"})
        return {"action": name, "id": _id(arguments)}

    if name == "add_note":
        arguments = _arguments(arguments, {"title", "body", "folder", "folder_id"})
        payload = {
            "action": name,
            "title": _text(arguments.get("title"), "title", 512, required=True),
            "body": _content(arguments, "body", 100000) or "",
        }
        _selector(arguments, payload, "folder", "folder_id")
        return payload

    if name == "append_to_note":
        arguments = _arguments(arguments, {"id", "text"})
        return {
            "action": name,
            "id": _id(arguments),
            "text": _text(
                arguments.get("text"),
                "text",
                50000,
                required=True,
                preserve=True,
            ),
        }

    if name == "rename_note":
        arguments = _arguments(arguments, {"id", "title"})
        return {
            "action": name,
            "id": _id(arguments),
            "title": _text(arguments.get("title"), "title", 512, required=True),
        }

    if name == "move_note":
        arguments = _arguments(arguments, {"id", "folder_id"})
        return {
            "action": name,
            "id": _id(arguments),
            "folder_id": _id(arguments, "folder_id"),
        }

    if name == "replace_note_content":
        arguments = _arguments(arguments, {"id", "title", "body"})
        payload = {
            "action": name,
            "id": _id(arguments),
            "body": _content(arguments, "body", 100000, required=True),
        }
        if "title" in arguments:
            payload["title"] = _text(
                arguments["title"], "title", 512, required=True
            )
        return payload

    raise UserError("unknown tool")


def invoke_notes(payload):
    try:
        completed = subprocess.run(
            [
                "/usr/bin/osascript",
                "-l",
                "JavaScript",
                str(BRIDGE),
                json.dumps(payload, ensure_ascii=False),
            ],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise UserError("Apple Notes did not respond within 120 seconds")
    except OSError as error:
        raise UserError("could not launch Apple Notes automation: %s" % error)

    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        detail = detail.splitlines()[-1] if detail else "unknown automation error"
        raise UserError("Apple Notes rejected the request: %s" % detail)

    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError:
        raise UserError("Apple Notes returned an unreadable response")
    if not isinstance(result, dict):
        raise UserError("Apple Notes returned an invalid response")
    return result


def _tool_result(text, structured=None, is_error=False):
    result = {"content": [{"type": "text", "text": text}]}
    if structured is not None:
        result["structuredContent"] = structured
    if is_error:
        result["isError"] = True
    return result


def call_tool(params):
    if not isinstance(params, dict) or params.get("name") not in TOOL_NAMES:
        raise UserError("unknown tool")
    name = params["name"]
    try:
        payload = normalize_arguments(name, params.get("arguments", {}))
        result = invoke_notes(payload)
    except UserError as error:
        return _tool_result(str(error), is_error=True)

    if name == "list_note_folders":
        message = "Found %d Notes accounts and %d folders." % (
            len(result.get("accounts", [])),
            len(result.get("folders", [])),
        )
    elif name == "create_note_folder":
        message = 'Created Notes folder “%s”.' % result.get("folder", {}).get(
            "name", "Notes"
        )
    elif name == "rename_note_folder":
        message = 'Renamed Notes folder to “%s”.' % result.get("folder", {}).get(
            "name", "Notes"
        )
    elif name == "search_notes":
        message = "Found %d matching notes." % len(result.get("notes", []))
    elif name == "get_note":
        note = result.get("note", {})
        message = '“%s” is in “%s”.' % (
            note.get("title", "Note"),
            note.get("folder", "Notes"),
        )
    elif name == "add_note":
        note = result.get("note", {})
        message = 'Created “%s” in “%s”.' % (
            note.get("title", "Note"),
            note.get("folder", "Notes"),
        )
    elif name == "append_to_note":
        message = 'Appended to “%s”.' % result.get("note", {}).get("title", "note")
    elif name == "rename_note":
        message = 'Renamed note to “%s”.' % result.get("note", {}).get(
            "title", "Note"
        )
    elif name == "move_note":
        note = result.get("note", {})
        message = 'Moved “%s” to “%s”.' % (
            note.get("title", "Note"),
            note.get("folder", "Notes"),
        )
    elif name == "replace_note_content":
        message = 'Replaced the content of “%s”.' % result.get("note", {}).get(
            "title", "note"
        )
    else:
        message = 'Deleted “%s”.' % result.get("deleted", {}).get("title", "note")
    return _tool_result(message, result)


def _response(message_id, result):
    return {"jsonrpc": "2.0", "id": message_id, "result": result}


def _error(message_id, code, message):
    return {
        "jsonrpc": "2.0",
        "id": message_id,
        "error": {"code": code, "message": message},
    }


def handle_message(message):
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        return _error(None, -32600, "Invalid Request")

    method = message.get("method")
    message_id = message.get("id")
    if message_id is None:
        return None

    if method == "initialize":
        return _response(
            message_id,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "apple-notes", "version": SERVER_VERSION},
                "instructions": (
                    "Reads and safely manages native Apple Notes. Search first, then "
                    "use exact note, folder, and account IDs for mutations. Shared and "
                    "password-protected notes are read-only. Prefer appending; content "
                    "replacement discards formatting and is blocked for attachments."
                ),
            },
        )
    if method == "ping":
        return _response(message_id, {})
    if method == "tools/list":
        return _response(message_id, {"tools": TOOLS})
    if method == "tools/call":
        try:
            return _response(message_id, call_tool(message.get("params")))
        except UserError as error:
            return _error(message_id, -32602, str(error))
    return _error(message_id, -32601, "Method not found")


def main():
    for raw_line in sys.stdin:
        try:
            message = json.loads(raw_line)
            response = handle_message(message)
        except json.JSONDecodeError:
            response = _error(None, -32700, "Parse error")
        except Exception as error:  # Keep one bad request from killing the process.
            print("apple-notes server error: %s" % error, file=sys.stderr)
            response = _error(None, -32603, "Internal error")
        if response is not None:
            print(
                json.dumps(response, ensure_ascii=False, separators=(",", ":")),
                flush=True,
            )


if __name__ == "__main__":
    main()
