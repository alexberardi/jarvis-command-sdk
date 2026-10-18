# Inbox attachments in the SDK

- Date: 2026-10-18
- Status: accepted
- Item: #186 (piece 3 of the ComfyUI plan; jarvisd is piece 1, see jarvis-server
  `docs/decisions/2026-10-17-inbox-attachments.md`; mobile #185, the node backend #187 and the
  package jarvis-cmd-comfyui #188 are the others)

## Context

jarvisd now stores files for inbox items. A node uploads each file first
(`POST /api/v0/node/inbox-attachment`, with the raw body and `Content-Type`), then creates the item
with `"attachment_ids": [...]`. Packages post inbox items through `JarvisInbox.post()`, which hands
everything to the node's `InboxBackend`. The SDK makes no HTTP calls itself. Packages need a way to
pass files through that facade without breaking existing packages or the nodes already installed.

## Decision

1. **`Attachment(data | path, mime, filename)`**, a frozen dataclass with exactly one of `data`
   (bytes) or `path`. A path lets a package hand over a large generated video without loading it
   into memory: `size` uses `os.stat`, and the magic-byte check reads only the first 16 bytes.
   `filename` defaults to the path's basename. `repr()` leaves out the bytes. The constructor never
   raises; a malformed attachment is reported by validation.
2. **The SDK validates against copies of jarvisd's defaults**: `ATTACHMENT_MAX_FILE_BYTES = 25 MiB`,
   `ATTACHMENT_MAX_ITEM_BYTES = 50 MiB`, and `ATTACHMENT_MIME_TYPES` = png, jpeg, webp, gif, mp4,
   webm. It also does a cheap magic-byte check that approximates jarvisd's content sniffing (an ISO-BMFF `ftyp`
   with a HEIC/AVIF/QuickTime brand is not `video/mp4`). This catches the common mistakes before
   an upload, with a tag that says what went wrong. **The server stays authoritative**: its caps are
   settings and can be lowered, so a file the SDK accepts can still be refused there, and the
   package gets the backend's failure tag.
3. **New tags, no exceptions** (the module's promise): `"attachment_type"` (the mime is not allowed,
   or the bytes do not match it), `"attachment_too_large"` (over the per-file or per-item cap),
   `"invalid"` (an existing tag: both or neither of data/path, a missing file, not an `Attachment`).
4. **`attachments=` is passed to the backend only when the list is non-empty.** Every existing call
   reaches every existing backend exactly as before, so a backend written before attachments still
   works. An empty list is the same as `None`.
5. **`"attachments_unsupported"`**: when attachments are given and the registered backend's
   `post_inbox_item` takes neither `attachments` nor `**kwargs` (checked with `inspect.signature`),
   `post()` returns this tag instead of raising a `TypeError`. A package on an older node fails
   cleanly and can tell the user to update the node.
6. **The backend's contract (#187)**: `InboxBackend.post_inbox_item` gains the keyword-only
   `attachments: list[Attachment] | None = None`. The method stays abstract under the same name, so
   existing subclasses still instantiate. The backend gets the list already validated. It uploads
   each file (`attachment.read_bytes()`, `Content-Type: attachment.mime`), collects the ids and
   sends them as `attachment_ids` on the inbox-item POST. If an upload fails, it returns a failure
   tag and does not create the item.

## Consequences

- Version 0.13.0 (a minor bump, additive). Packages that use attachments should require
  `jarvis-command-sdk>=0.13.0`.
- The caps and types are duplicated from jarvisd. If jarvisd's defaults change, these constants
  should follow, though the server stays correct either way.
- The tag names are shared with #187 and #188. Keep them in step.
