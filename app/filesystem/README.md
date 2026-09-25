# Filesystem boundary

Hermes exposes only three read-only tools: `list_directory`, `search_files`,
and `read_file`. Every operation uses `PathSecurityLayer` to normalize and
resolve paths, enforce configured roots, reject traversal and symlink/junction
escapes, block sensitive names/extensions, and enforce the configured file-size
limit. Every operation also passes through `PermissionEngine`.

There are no write, delete, move, rename, terminal, browser, or arbitrary-code
operations.