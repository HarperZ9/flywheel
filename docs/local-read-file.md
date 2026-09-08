# Local read_file paging

`ToolExecutor.read_file` keeps the old plain-text result for small files that
fit in the executor output budget. Larger reads return:

```text
READ_FILE_META {"schema":"flywheel.read_file/v1",...}
<file text page>
```

The metadata line is compact and appears before content, so continuation data
survives output truncation. It reports byte `offset`, returned `bytes`, total
`size`, `truncated`, `next_offset`, UTF-8 encoding, and a stat identity made from
`size` plus `mtime_ns`. That identity is a drift signal, not a cryptographic file
proof.

Before reading bytes, the tool binds the opened file descriptor to the configured
root using the host's handle-final-path primitive. Hosts without that primitive
fail closed with `[error] read_file_handle_path_unsupported`.
Windows uses `GetFinalPathNameByHandleW`; Linux uses `/proc/self/fd`; macOS
uses `fcntl(F_GETPATH)` with a bounded 1024-byte buffer. Apple documents the
descriptor path operation in its [fcntl manual](https://developer.apple.com/library/archive/documentation/System/Conceptual/ManPages_iPhoneOS/man2/fcntl.2.html),
with the command and buffer bounds defined in [fcntl.h](https://github.com/apple-oss-distributions/xnu/blob/main/bsd/sys/fcntl.h)
and [param.h](https://github.com/apple-oss-distributions/xnu/blob/main/bsd/sys/param.h),
which uses `PATH_MAX` from [syslimits.h](https://github.com/apple-oss-distributions/xnu/blob/main/bsd/sys/syslimits.h).
An unavailable or malformed descriptor path fails closed; there is no
pathname-only fallback.

Optional arguments:

- `offset`: zero-based byte offset. Use the previous `next_offset` to continue.
- `max_bytes`: requested byte budget, capped at 1 MiB and still bounded by the
  executor output budget.
- `if_identity`: pass exactly the previous metadata `identity` keys to fail
  closed when the reported stat identity changes between pages.

The model's tool instructions describe this continuation protocol: follow
`next_offset` with `if_identity` while `truncated` is true. On source drift,
discard the partial assembly and start a fresh read.

Errors are fixed codes such as `[error] read_file_path_escaped`,
`[error] read_file_source_drift`, or `[error] read_file_offset_invalid`. They do
not include host paths or child exception strings.
