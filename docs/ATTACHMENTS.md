# Attachment Storage and Document Intelligence

Fugu stores attachment metadata and structured processing results in PostgreSQL. Original binary files are stored only in a private object store.

## Storage configuration

Attachment storage is disabled unless `ATTACHMENT_STORAGE_BACKEND` is configured.

### Production: S3-compatible private storage

```env
ATTACHMENT_STORAGE_BACKEND=s3-compatible
ATTACHMENT_STORAGE_BUCKET=fugu-attachments
ATTACHMENT_STORAGE_S3_ENDPOINT_URL=https://<account-or-provider-endpoint>
ATTACHMENT_STORAGE_S3_REGION=auto
ATTACHMENT_STORAGE_S3_ACCESS_KEY_ID=<write-and-read-key>
ATTACHMENT_STORAGE_S3_SECRET_ACCESS_KEY=<secret>
ATTACHMENT_MAX_FILE_SIZE_BYTES=26214400
```

The bucket must remain private. Fugu performs controlled authenticated upload, download, inspection, and deletion through the backend. Storage credentials, bucket names, and object keys are never returned by the attachment API.

The S3-compatible implementation can be used with providers such as Cloudflare R2, AWS S3, and other services that expose the standard S3 object API. Provider-specific bucket creation, CORS, retention, and lifecycle policies remain deployment responsibilities.

### Development: local private storage

```env
ATTACHMENT_STORAGE_BACKEND=local
ATTACHMENT_STORAGE_BUCKET=fugu-attachments
ATTACHMENT_STORAGE_LOCAL_ROOT=.fugu/attachments
ATTACHMENT_MAX_FILE_SIZE_BYTES=26214400
```

Local storage is intended for development and isolated testing. Render's ephemeral filesystem is not a production attachment store.

## Supported first-release formats

- PDF
- PNG, JPEG, and WebP
- TXT and Markdown
- CSV and XLSX
- DOCX
- Common UTF-8 source-code formats, including Python, JavaScript, TypeScript, Java, C/C++, C#, Go, Rust, Ruby, PHP, Swift, Kotlin, SQL, shell, JSON, YAML, XML, HTML, and CSS

Executable signatures, unsupported extensions, extension/MIME mismatches, malformed binary signatures, binary null bytes in text files, and oversized files are rejected before storage.

## Structured processing

Fugu preserves format-specific structure instead of flattening all files into one text field:

- PDF: ordered pages, page text, and metadata
- DOCX: paragraphs and tables
- XLSX: sheets, rows, columns, and cell values
- CSV: rows and columns
- text and source: ordered lines and language identifier
- images: verified format, dimensions, color mode, and native multimodal marker

Processing is deliberately bounded. Large documents receive explicit truncation warnings. Encrypted PDFs are rejected. OCR and arbitrary archive extraction are not used in the first release.

## Pipeline behavior

Selected attachments are validated against the authenticated user and thread before execution. Each run stores an immutable metadata and structured-content snapshot with the attachment SHA-256 hash.

Only the Reader stage receives structured attachment content. Downstream stages receive the Reader's interpretation through normal pipeline dependencies and do not independently reprocess raw files.

Private image bytes are integrity-checked, encoded only in memory, and sent only to a Reader model whose backend catalogue advertises image understanding. Image execution is rejected before provider access when the Reader or configured fallback lacks vision support.

Whole-run retries reuse the exact recorded attachment snapshot and verify current object hashes. Downstream stage retries do not reload raw files.

## Deferred production verification

Repository CI validates schema, storage contracts, processing, ownership, provider payloads, browser behavior, and container construction. Final verification of the live Vercel, Render, Neon, object-storage, and real-provider configuration is deferred until all roadmap implementation phases are complete.
