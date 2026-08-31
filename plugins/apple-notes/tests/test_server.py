import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock


PLUGIN_DIR = Path(__file__).resolve().parents[1]
SERVER_PATH = PLUGIN_DIR / "server.py"
BRIDGE_PATH = PLUGIN_DIR / "notes.js"
SPEC = importlib.util.spec_from_file_location("apple_notes_server", SERVER_PATH)
server = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(server)


class ArgumentValidationTests(unittest.TestCase):
    def test_list_folders_has_no_arguments(self):
        self.assertEqual(
            server.normalize_arguments("list_note_folders", {}),
            {"action": "list_note_folders"},
        )

    def test_create_folder_selects_account_by_id(self):
        payload = server.normalize_arguments(
            "create_note_folder",
            {"name": "Projects", "account_id": "account-id"},
        )
        self.assertEqual(
            payload,
            {
                "action": "create_note_folder",
                "name": "Projects",
                "account_id": "account-id",
            },
        )

    def test_search_defaults_are_bounded(self):
        payload = server.normalize_arguments("search_notes", {})
        self.assertEqual(payload["limit"], 25)
        self.assertEqual(payload["offset"], 0)
        self.assertFalse(payload["include_subfolders"])
        self.assertIsNone(payload["query"])

    def test_search_accepts_filters_and_normalizes_offsets(self):
        payload = server.normalize_arguments(
            "search_notes",
            {
                "query": " launch ",
                "account": "iCloud",
                "folder": "Projects",
                "include_subfolders": True,
                "modified_after": "2026-09-01T00:00:00-04:00",
                "modified_before": "2026-10-01T00:00:00-04:00",
                "offset": 10,
                "limit": 50,
            },
        )
        self.assertEqual(payload["query"], "launch")
        self.assertEqual(payload["account"], "iCloud")
        self.assertEqual(payload["folder"], "Projects")
        self.assertTrue(payload["include_subfolders"])
        self.assertEqual(payload["offset"], 10)
        self.assertEqual(payload["limit"], 50)

    def test_rejects_ambiguous_account_and_folder_selectors(self):
        with self.assertRaisesRegex(server.UserError, "either account or account_id"):
            server.normalize_arguments(
                "search_notes", {"account": "iCloud", "account_id": "a"}
            )
        with self.assertRaisesRegex(server.UserError, "either folder or folder_id"):
            server.normalize_arguments(
                "add_note",
                {
                    "title": "Draft",
                    "folder": "Projects",
                    "folder_id": "f",
                },
            )

    def test_rejects_naive_and_backwards_modification_ranges(self):
        with self.assertRaisesRegex(server.UserError, "UTC offset"):
            server.normalize_arguments(
                "search_notes", {"modified_after": "2026-09-01T12:00:00"}
            )
        with self.assertRaisesRegex(server.UserError, "before modified_before"):
            server.normalize_arguments(
                "search_notes",
                {
                    "modified_after": "2026-09-02T00:00:00Z",
                    "modified_before": "2026-09-01T00:00:00Z",
                },
            )

    def test_rejects_unknown_arguments_and_boolean_integer(self):
        with self.assertRaisesRegex(server.UserError, "unknown argument"):
            server.normalize_arguments("list_note_folders", {"surprise": True})
        with self.assertRaisesRegex(server.UserError, "limit must be an integer"):
            server.normalize_arguments("search_notes", {"limit": True})

    def test_plaintext_body_is_preserved_and_may_be_empty(self):
        payload = server.normalize_arguments(
            "add_note", {"title": " Draft ", "body": "  first\nsecond  "}
        )
        self.assertEqual(payload["title"], "Draft")
        self.assertEqual(payload["body"], "  first\nsecond  ")
        replaced = server.normalize_arguments(
            "replace_note_content", {"id": "note-id", "body": ""}
        )
        self.assertEqual(replaced["body"], "")

    def test_append_rejects_blank_text(self):
        with self.assertRaisesRegex(server.UserError, "text cannot be empty"):
            server.normalize_arguments(
                "append_to_note", {"id": "note-id", "text": "  \n "}
            )

    def test_content_rejects_null_bytes_and_size_overflow(self):
        with self.assertRaisesRegex(server.UserError, "null byte"):
            server.normalize_arguments(
                "add_note", {"title": "Draft", "body": "bad\x00body"}
            )
        with self.assertRaisesRegex(server.UserError, "at most 50000"):
            server.normalize_arguments(
                "append_to_note", {"id": "n", "text": "x" * 50001}
            )

    def test_move_requires_exact_folder_id(self):
        with self.assertRaisesRegex(server.UserError, "folder_id must be a string"):
            server.normalize_arguments("move_note", {"id": "note-id"})


class ProtocolTests(unittest.TestCase):
    def test_initialize_and_tool_list(self):
        initialized = server.handle_message(
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
        )
        self.assertEqual(
            initialized["result"]["protocolVersion"], server.PROTOCOL_VERSION
        )
        self.assertEqual(initialized["result"]["serverInfo"]["version"], "0.1.0")

        listed = server.handle_message(
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
        )
        tools = listed["result"]["tools"]
        self.assertEqual(
            [tool["name"] for tool in tools],
            [
                "list_note_folders",
                "create_note_folder",
                "rename_note_folder",
                "search_notes",
                "get_note",
                "add_note",
                "append_to_note",
                "rename_note",
                "move_note",
                "replace_note_content",
                "delete_note",
            ],
        )
        for tool in tools:
            self.assertFalse(tool["annotations"]["openWorldHint"])
        replace = next(
            tool for tool in tools if tool["name"] == "replace_note_content"
        )
        delete = next(tool for tool in tools if tool["name"] == "delete_note")
        append = next(tool for tool in tools if tool["name"] == "append_to_note")
        self.assertTrue(replace["annotations"]["destructiveHint"])
        self.assertTrue(delete["annotations"]["destructiveHint"])
        self.assertFalse(delete["annotations"]["idempotentHint"])
        self.assertFalse(append["annotations"]["idempotentHint"])

    @mock.patch.object(server, "invoke_notes")
    def test_tool_call_returns_structured_content(self, invoke):
        invoke.return_value = {
            "note": {"id": "note-id", "title": "Project brief", "folder": "Work"}
        }
        result = server.call_tool(
            {"name": "get_note", "arguments": {"id": "note-id"}}
        )
        self.assertNotIn("isError", result)
        self.assertEqual(result["structuredContent"]["note"]["id"], "note-id")
        self.assertIn("Project brief", result["content"][0]["text"])
        invoke.assert_called_once_with({"action": "get_note", "id": "note-id"})

    def test_validation_failure_is_a_tool_error(self):
        result = server.call_tool(
            {"name": "append_to_note", "arguments": {"id": "n", "text": ""}}
        )
        self.assertTrue(result["isError"])
        self.assertIn("cannot be empty", result["content"][0]["text"])

    def test_json_lines_server_round_trip(self):
        requests = "\n".join(
            [
                json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"}),
                json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}),
            ]
        )
        completed = subprocess.run(
            [sys.executable, str(SERVER_PATH)],
            input=requests + "\n",
            text=True,
            capture_output=True,
            timeout=10,
            check=True,
        )
        responses = [json.loads(line) for line in completed.stdout.splitlines()]
        self.assertEqual([response["id"] for response in responses], [1, 2])
        self.assertEqual(len(responses[1]["result"]["tools"]), 11)

    def test_malformed_and_unknown_messages_do_not_kill_protocol(self):
        invalid = server.handle_message({"hello": "world"})
        unknown = server.handle_message(
            {"jsonrpc": "2.0", "id": 9, "method": "unknown"}
        )
        self.assertEqual(invalid["error"]["code"], -32600)
        self.assertEqual(unknown["error"]["code"], -32601)


class JavaScriptBridgeTests(unittest.TestCase):
    def run_bridge_harness(self, expression):
        source = BRIDGE_PATH.read_text(encoding="utf-8")
        harness = "function run(argv) { return JSON.stringify(" + expression + "); }"
        completed = subprocess.run(
            ["/usr/bin/osascript", "-l", "JavaScript", "-e", source, "-e", harness],
            text=True,
            capture_output=True,
            timeout=20,
            check=True,
        )
        return json.loads(completed.stdout)

    def test_html_escaping_is_literal(self):
        result = self.run_bridge_harness(
            "escapeHtml('<script> & \\\"quotes\\\" \\\'apostrophe\\\'')"
        )
        self.assertEqual(
            result,
            "&lt;script&gt; &amp; &quot;quotes&quot; &#39;apostrophe&#39;",
        )

    def test_note_html_uses_title_and_plaintext_lines(self):
        result = self.run_bridge_harness(
            "noteHtml('Project <brief>', 'First line\\n\\nSecond & final')"
        )
        self.assertEqual(
            result,
            "<h1>Project &lt;brief&gt;</h1>"
            "<div>First line</div><div><br></div><div>Second &amp; final</div>",
        )

    def test_empty_note_body_keeps_an_editable_line(self):
        result = self.run_bridge_harness("noteHtml('Draft', '')")
        self.assertEqual(result, "<h1>Draft</h1><div><br></div>")

    def test_edit_safety_blocks_locked_shared_and_shared_folder_notes(self):
        result = self.run_bridge_harness(
            "(() => {"
            "const message = (note) => { try { ensureEditableNote(note); return null; } "
            "catch (error) { return error.message; } };"
            "const folder = (shared) => ({shared:()=>shared,name:()=> 'Work'});"
            "return {"
            "locked:message({passwordProtected:()=>true,shared:()=>false,container:()=>folder(false)}),"
            "shared:message({passwordProtected:()=>false,shared:()=>true,container:()=>folder(false)}),"
            "shared_folder:message({passwordProtected:()=>false,shared:()=>false,container:()=>folder(true)}),"
            "editable:message({passwordProtected:()=>false,shared:()=>false,container:()=>folder(false)})};"
            "})()"
        )
        self.assertIn("Password-protected", result["locked"])
        self.assertIn("Shared notes", result["shared"])
        self.assertIn("Shared folder", result["shared_folder"])
        self.assertIsNone(result["editable"])

    def test_replace_safety_blocks_attachments(self):
        result = self.run_bridge_harness(
            "(() => {"
            "const folder={shared:()=>false,name:()=> 'Work'};"
            "const note={passwordProtected:()=>false,shared:()=>false,container:()=>folder,"
            "attachments:()=>[{}]};"
            "try { ensureReplaceableNote(note); return null; }"
            "catch (error) { return error.message; }"
            "})()"
        )
        self.assertIn("attachments", result)
        self.assertIn("append_to_note", result)

    def test_search_filters_text_and_sorts_by_modification_time(self):
        result = self.run_bridge_harness(
            "(() => {"
            "objectKind=(value)=>value.kind;"
            "const account={kind:'account',id:()=> 'a',name:()=> 'iCloud'};"
            "const folder={kind:'folder',id:()=> 'f',name:()=> 'Projects',"
            "container:()=>account,shared:()=>false};"
            "const make=(id,title,plain,modified)=>({id:()=>id,name:()=>title,"
            "plaintext:()=>plain,body:()=>'',container:()=>folder,attachments:()=>[],"
            "passwordProtected:()=>false,shared:()=>false,creationDate:()=>new Date(modified),"
            "modificationDate:()=>new Date(modified)});"
            "const all=["
            "make('old','Launch draft','launch plan','2026-09-01T12:00:00Z'),"
            "make('new','Launch brief','final launch','2026-09-03T12:00:00Z'),"
            "make('skip','Other','nothing here','2026-09-04T12:00:00Z')];"
            "const notes=()=>{throw new Error('unbounded note scan');};"
            "notes.whose=(predicate)=>()=>all.filter((note)=>{"
            "const query=predicate._or[0].name._contains.toLocaleLowerCase();"
            "return note.name().toLocaleLowerCase().includes(query)||"
            "note.plaintext().toLocaleLowerCase().includes(query);});"
            "const app={notes};"
            "return searchNotes(app,{query:'launch',include_subfolders:false,offset:0,limit:10});"
            "})()"
        )
        self.assertEqual([note["id"] for note in result["notes"]], ["new", "old"])
        self.assertEqual(result["total_matches"], 2)
        self.assertFalse(result["truncated"])


if __name__ == "__main__":
    unittest.main()
