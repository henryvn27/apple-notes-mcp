function text(value) {
  return value === null || value === undefined ? "" : String(value);
}

function safe(read, fallback) {
  try {
    const value = read();
    return value === null || value === undefined ? fallback : value;
  } catch (error) {
    return fallback;
  }
}

function isoDate(value) {
  return value ? new Date(value).toISOString() : null;
}

function escapeHtml(value) {
  return text(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function textBodyHtml(value) {
  return text(value)
    .split(/\r?\n/)
    .map((line) => (line ? `<div>${escapeHtml(line)}</div>` : "<div><br></div>"))
    .join("");
}

function noteHtml(title, body) {
  const content = textBodyHtml(body);
  return `<h1>${escapeHtml(title)}</h1>${content || "<div><br></div>"}`;
}

function objectKind(value) {
  const display = Automation.getDisplayString(value);
  if (display.includes(".accounts.byId(")) return "account";
  if (display.includes(".folders.byId(")) return "folder";
  if (display.includes(".notes.byId(")) return "note";
  return "unknown";
}

function exactAccountId(notes, id) {
  const account = notes.accounts.byId(id);
  try {
    if (account.id() === id) return account;
  } catch (error) {}
  throw new Error(`No Notes account with ID “${id}” exists.`);
}

function exactAccount(notes, name) {
  const wanted = name.toLocaleLowerCase();
  const matches = notes.accounts().filter(
    (account) => text(account.name()).toLocaleLowerCase() === wanted,
  );
  if (matches.length === 0) {
    throw new Error(`No Notes account named “${name}” exists.`);
  }
  if (matches.length > 1) {
    throw new Error(`More than one Notes account is named “${name}”. Use account_id.`);
  }
  return matches[0];
}

function selectedAccount(notes, input) {
  if (input.account_id) return exactAccountId(notes, input.account_id);
  if (input.account) return exactAccount(notes, input.account);
  return notes.defaultAccount();
}

function exactFolderId(notes, id) {
  const folder = notes.folders.byId(id);
  try {
    if (folder.id() === id) return folder;
  } catch (error) {}
  throw new Error(`No Notes folder with ID “${id}” exists.`);
}

function accountForFolder(folder) {
  let current = folder;
  for (let depth = 0; depth < 64; depth += 1) {
    current = current.container();
    const kind = objectKind(current);
    if (kind === "account") return current;
    if (kind !== "folder") break;
  }
  throw new Error("Notes returned an unreadable folder hierarchy.");
}

function folderParentId(folder) {
  const container = folder.container();
  return objectKind(container) === "folder" ? container.id() : null;
}

function folderBelongsTo(folder, accountId) {
  return accountForFolder(folder).id() === accountId;
}

function exactFolder(notes, name, account) {
  const wanted = name.toLocaleLowerCase();
  const matches = notes.folders().filter((folder) => {
    if (text(folder.name()).toLocaleLowerCase() !== wanted) return false;
    return !account || folderBelongsTo(folder, account.id());
  });
  if (matches.length === 0) {
    throw new Error(`No Notes folder named “${name}” exists.`);
  }
  if (matches.length > 1) {
    throw new Error(`More than one Notes folder is named “${name}”. Use folder_id.`);
  }
  return matches[0];
}

function selectedFolder(notes, input) {
  const account = input.account || input.account_id
    ? selectedAccount(notes, input)
    : null;
  let folder;
  if (input.folder_id) {
    folder = exactFolderId(notes, input.folder_id);
  } else if (input.folder) {
    folder = exactFolder(notes, input.folder, account);
  } else if (account) {
    folder = account.defaultFolder();
  } else {
    folder = notes.defaultAccount().defaultFolder();
  }
  if (account && !folderBelongsTo(folder, account.id())) {
    throw new Error(`Folder “${folder.name()}” is not in account “${account.name()}”.`);
  }
  return folder;
}

function findNote(notes, id) {
  const note = notes.notes.byId(id);
  try {
    if (note.id() === id) {
      return { note, folder: note.container() };
    }
  } catch (error) {}
  throw new Error(`No note with ID “${id}” exists.`);
}

function ensureWritableFolder(folder) {
  if (Boolean(safe(() => folder.shared(), false))) {
    throw new Error(`Shared folder “${folder.name()}” is read-only in this plugin.`);
  }
}

function ensureEditableNote(note) {
  if (Boolean(safe(() => note.passwordProtected(), false))) {
    throw new Error("Password-protected notes are read-only in this plugin.");
  }
  if (Boolean(safe(() => note.shared(), false))) {
    throw new Error("Shared notes are read-only in this plugin.");
  }
  ensureWritableFolder(note.container());
}

function ensureReplaceableNote(note) {
  ensureEditableNote(note);
  if (safe(() => note.attachments(), []).length > 0) {
    throw new Error(
      "Notes with attachments cannot have their content replaced; use append_to_note.",
    );
  }
}

function serializeAccount(notes, account) {
  return {
    id: account.id(),
    name: text(account.name()),
    upgraded: Boolean(safe(() => account.upgraded(), false)),
    default: account.id() === notes.defaultAccount().id(),
    default_folder_id: safe(() => account.defaultFolder().id(), null),
    note_count: safe(() => account.notes().length, null),
  };
}

function serializeFolder(notes, folder) {
  const account = accountForFolder(folder);
  return {
    id: folder.id(),
    name: text(folder.name()),
    account: text(account.name()),
    account_id: account.id(),
    parent_folder_id: folderParentId(folder),
    shared: Boolean(safe(() => folder.shared(), false)),
    default: safe(() => account.defaultFolder().id() === folder.id(), false),
    note_count: safe(() => folder.notes().length, null),
  };
}

function serializeAttachment(attachment) {
  return {
    id: text(safe(() => attachment.id(), "")),
    name: text(safe(() => attachment.name(), "")),
    content_identifier: text(safe(() => attachment.contentIdentifier(), "")) || null,
    url: text(safe(() => attachment.url(), "")) || null,
    shared: Boolean(safe(() => attachment.shared(), false)),
    created_at: isoDate(safe(() => attachment.creationDate(), null)),
    modified_at: isoDate(safe(() => attachment.modificationDate(), null)),
  };
}

function noteMetadata(note, folder) {
  const account = accountForFolder(folder);
  const locked = Boolean(safe(() => note.passwordProtected(), false));
  const plain = locked ? null : text(safe(() => note.plaintext(), ""));
  const attachments = safe(() => note.attachments(), []);
  return {
    id: note.id(),
    title: text(note.name()),
    folder: text(folder.name()),
    folder_id: folder.id(),
    account: text(account.name()),
    account_id: account.id(),
    created_at: isoDate(safe(() => note.creationDate(), null)),
    modified_at: isoDate(safe(() => note.modificationDate(), null)),
    password_protected: locked,
    shared: Boolean(safe(() => note.shared(), false)),
    attachment_count: attachments.length,
    preview: plain === null ? null : plain.replace(/\s+/g, " ").trim().slice(0, 280),
  };
}

function serializeNote(note, folder) {
  const metadata = noteMetadata(note, folder);
  const locked = metadata.password_protected;
  return {
    ...metadata,
    plaintext: locked ? null : text(safe(() => note.plaintext(), "")),
    body_html: locked ? null : text(safe(() => note.body(), "")),
    attachments: locked
      ? []
      : safe(() => note.attachments(), []).map(serializeAttachment),
  };
}

function listNoteFolders(notes) {
  return {
    accounts: notes.accounts().map((account) => serializeAccount(notes, account)),
    folders: notes.folders().map((folder) => serializeFolder(notes, folder)),
  };
}

function duplicateFolder(folder, name, currentId) {
  const wanted = name.toLocaleLowerCase();
  return folder.container().folders().find(
    (candidate) =>
      text(candidate.name()).toLocaleLowerCase() === wanted &&
      candidate.id() !== currentId,
  );
}

function createNoteFolder(notes, input) {
  const account = selectedAccount(notes, input);
  const duplicate = account.folders().find(
    (folder) => text(folder.name()).toLocaleLowerCase() === input.name.toLocaleLowerCase(),
  );
  if (duplicate) {
    throw new Error(`A top-level Notes folder named “${input.name}” already exists.`);
  }
  const folder = notes.Folder({ name: input.name });
  account.folders.push(folder);
  return { folder: serializeFolder(notes, folder) };
}

function renameNoteFolder(notes, input) {
  const folder = exactFolderId(notes, input.id);
  ensureWritableFolder(folder);
  if (duplicateFolder(folder, input.name, folder.id())) {
    throw new Error(`A sibling Notes folder named “${input.name}” already exists.`);
  }
  folder.name = input.name;
  return { folder: serializeFolder(notes, folder) };
}

function folderDescendsFrom(folder, ancestorId) {
  let current = folder;
  for (let depth = 0; depth < 64; depth += 1) {
    if (current.id() === ancestorId) return true;
    const container = current.container();
    if (objectKind(container) !== "folder") return false;
    current = container;
  }
  return false;
}

function notesMatchingQuery(notes, query) {
  if (!query) return notes.notes();
  return notes.notes.whose({
    _or: [
      { name: { _contains: query } },
      { plaintext: { _contains: query } },
    ],
  })();
}

function searchNotes(notes, input) {
  const account = input.account || input.account_id
    ? selectedAccount(notes, input)
    : null;
  const folder = input.folder || input.folder_id
    ? selectedFolder(notes, input)
    : null;
  const query = input.query || null;
  const modifiedAfter = input.modified_after
    ? new Date(input.modified_after).getTime()
    : null;
  const modifiedBefore = input.modified_before
    ? new Date(input.modified_before).getTime()
    : null;
  const matches = [];

  for (const note of notesMatchingQuery(notes, query)) {
    const noteFolder = safe(() => note.container(), null);
    if (!noteFolder) continue;
    if (account && !folderBelongsTo(noteFolder, account.id())) continue;
    if (folder) {
      const matchesFolder = input.include_subfolders
        ? folderDescendsFrom(noteFolder, folder.id())
        : noteFolder.id() === folder.id();
      if (!matchesFolder) continue;
    }
    const modified = safe(() => new Date(note.modificationDate()).getTime(), 0);
    if (modifiedAfter !== null && modified < modifiedAfter) continue;
    if (modifiedBefore !== null && modified >= modifiedBefore) continue;
    matches.push({ note, folder: noteFolder, modified });
  }

  matches.sort((left, right) => {
    if (left.modified !== right.modified) return right.modified - left.modified;
    return text(left.note.name()).localeCompare(text(right.note.name()));
  });
  const page = matches.slice(input.offset, input.offset + input.limit);
  const truncated = input.offset + page.length < matches.length;
  return {
    notes: page.map((item) => noteMetadata(item.note, item.folder)),
    count: page.length,
    total_matches: matches.length,
    truncated,
    next_offset: truncated ? input.offset + page.length : null,
  };
}

function addNote(notes, input) {
  const folder = selectedFolder(notes, input);
  ensureWritableFolder(folder);
  const note = notes.Note({ body: noteHtml(input.title, input.body) });
  folder.notes.push(note);
  return { note: serializeNote(note, folder) };
}

function appendToNote(notes, input) {
  const record = findNote(notes, input.id);
  ensureEditableNote(record.note);
  const existing = text(safe(() => record.note.body(), ""));
  record.note.body = `${existing}<div><br></div>${textBodyHtml(input.text)}`;
  return { note: serializeNote(record.note, record.folder) };
}

function renameNote(notes, input) {
  const record = findNote(notes, input.id);
  ensureEditableNote(record.note);
  record.note.name = input.title;
  return { note: serializeNote(record.note, record.folder) };
}

function moveNote(notes, input) {
  let record = findNote(notes, input.id);
  ensureEditableNote(record.note);
  const folder = exactFolderId(notes, input.folder_id);
  ensureWritableFolder(folder);
  if (record.folder.id() !== folder.id()) {
    notes.move(record.note, { to: folder });
    record = findNote(notes, input.id);
  }
  return { note: serializeNote(record.note, record.folder) };
}

function replaceNoteContent(notes, input) {
  const record = findNote(notes, input.id);
  ensureReplaceableNote(record.note);
  const title = input.title || record.note.name();
  record.note.body = noteHtml(title, input.body);
  return { note: serializeNote(record.note, record.folder) };
}

function run(argv) {
  const input = JSON.parse(argv[0]);
  const notes = Application("Notes");

  switch (input.action) {
    case "list_note_folders":
      return JSON.stringify(listNoteFolders(notes));
    case "create_note_folder":
      return JSON.stringify(createNoteFolder(notes, input));
    case "rename_note_folder":
      return JSON.stringify(renameNoteFolder(notes, input));
    case "search_notes":
      return JSON.stringify(searchNotes(notes, input));
    case "get_note": {
      const record = findNote(notes, input.id);
      return JSON.stringify({ note: serializeNote(record.note, record.folder) });
    }
    case "add_note":
      return JSON.stringify(addNote(notes, input));
    case "append_to_note":
      return JSON.stringify(appendToNote(notes, input));
    case "rename_note":
      return JSON.stringify(renameNote(notes, input));
    case "move_note":
      return JSON.stringify(moveNote(notes, input));
    case "replace_note_content":
      return JSON.stringify(replaceNoteContent(notes, input));
    case "delete_note": {
      const record = findNote(notes, input.id);
      ensureEditableNote(record.note);
      const deleted = noteMetadata(record.note, record.folder);
      notes.delete(record.note);
      return JSON.stringify({ deleted });
    }
    default:
      throw new Error("Unsupported note action.");
  }
}
