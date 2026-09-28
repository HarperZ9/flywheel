#include "owned_gateway_cleanup.h"

#include <windows.h>
#include <tlhelp32.h>

#include <algorithm>
#include <cstdint>
#include <cwctype>
#include <string>
#include <vector>

namespace {

struct ProcessRow {
  DWORD pid;
  DWORD parent_pid;
  uint64_t creation_time;
};

struct SnapshotRows {
  uint64_t captured_at;
  std::vector<ProcessRow> rows;
};

struct OwnedProcess {
  DWORD pid;
  uint64_t creation_time;
  HANDLE handle;

  OwnedProcess(DWORD process_id, uint64_t created, HANDLE process_handle)
      : pid(process_id), creation_time(created), handle(process_handle) {}

  OwnedProcess(const OwnedProcess&) = delete;
  OwnedProcess& operator=(const OwnedProcess&) = delete;

  OwnedProcess(OwnedProcess&& other) noexcept
      : pid(other.pid), creation_time(other.creation_time), handle(other.handle) {
    other.handle = nullptr;
  }

  OwnedProcess& operator=(OwnedProcess&& other) noexcept {
    if (this != &other) {
      if (handle) {
        CloseHandle(handle);
      }
      pid = other.pid;
      creation_time = other.creation_time;
      handle = other.handle;
      other.handle = nullptr;
    }
    return *this;
  }

  ~OwnedProcess() {
    if (handle) {
      CloseHandle(handle);
    }
  }
};

std::wstring Lower(std::wstring value) {
  std::transform(value.begin(), value.end(), value.begin(), [](wchar_t c) {
    return static_cast<wchar_t>(std::towlower(c));
  });
  return value;
}

std::wstring StripLongPrefix(std::wstring value) {
  constexpr wchar_t prefix[] = L"\\\\?\\";
  if (value.rfind(prefix, 0) == 0) {
    return value.substr(4);
  }
  return value;
}

std::wstring FullPath(std::wstring value) {
  if (value.empty()) {
    return L"";
  }
  DWORD size = GetFullPathNameW(value.c_str(), 0, nullptr, nullptr);
  if (size == 0) {
    return StripLongPrefix(value);
  }
  std::wstring out(size, L'\0');
  DWORD written = GetFullPathNameW(value.c_str(), size, out.data(), nullptr);
  if (written == 0 || written >= size) {
    return StripLongPrefix(value);
  }
  out.resize(written);
  return StripLongPrefix(out);
}

std::wstring CurrentExeDir() {
  std::wstring buffer(MAX_PATH, L'\0');
  DWORD written = GetModuleFileNameW(nullptr, buffer.data(),
                                     static_cast<DWORD>(buffer.size()));
  while (written == buffer.size()) {
    buffer.resize(buffer.size() * 2, L'\0');
    written = GetModuleFileNameW(nullptr, buffer.data(),
                                 static_cast<DWORD>(buffer.size()));
  }
  if (written == 0) {
    return L"";
  }
  buffer.resize(written);
  size_t slash = buffer.find_last_of(L"\\/");
  return slash == std::wstring::npos ? L"" : buffer.substr(0, slash);
}

std::wstring ExpectedGatewayPath() {
  std::wstring dir = CurrentExeDir();
  if (dir.empty()) {
    return L"";
  }
  return FullPath(dir + L"\\engine\\flywheel-gateway.exe");
}

uint64_t CreationTime(HANDLE process) {
  FILETIME created;
  FILETIME exited;
  FILETIME kernel;
  FILETIME user;
  if (!GetProcessTimes(process, &created, &exited, &kernel, &user)) {
    return 0;
  }
  ULARGE_INTEGER value;
  value.LowPart = created.dwLowDateTime;
  value.HighPart = created.dwHighDateTime;
  return value.QuadPart;
}

uint64_t CurrentFileTime() {
  FILETIME now;
  GetSystemTimeAsFileTime(&now);
  ULARGE_INTEGER value;
  value.LowPart = now.dwLowDateTime;
  value.HighPart = now.dwHighDateTime;
  return value.QuadPart;
}

std::wstring ProcessImagePath(HANDLE process) {
  std::wstring path(32768, L'\0');
  DWORD size = static_cast<DWORD>(path.size());
  BOOL ok = QueryFullProcessImageNameW(process, 0, path.data(), &size);
  if (!ok || size == 0) {
    return L"";
  }
  path.resize(size);
  return FullPath(path);
}

bool SamePath(const std::wstring& left, const std::wstring& right) {
  return !left.empty() && !right.empty() && Lower(left) == Lower(right);
}

uint64_t ProcessCreationTime(DWORD pid) {
  HANDLE process = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, FALSE, pid);
  if (!process) {
    return 0;
  }
  uint64_t created = CreationTime(process);
  CloseHandle(process);
  return created;
}

SnapshotRows ProcessSnapshot() {
  SnapshotRows snapshot_rows{0, {}};
  uint64_t captured_at = CurrentFileTime();
  if (captured_at == 0) {
    return snapshot_rows;
  }
  HANDLE snapshot = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
  if (snapshot == INVALID_HANDLE_VALUE) {
    return snapshot_rows;
  }
  snapshot_rows.captured_at = captured_at;
  PROCESSENTRY32W entry;
  entry.dwSize = sizeof(PROCESSENTRY32W);
  if (Process32FirstW(snapshot, &entry)) {
    do {
      uint64_t created = ProcessCreationTime(entry.th32ProcessID);
      if (created != 0 && created < snapshot_rows.captured_at) {
        snapshot_rows.rows.push_back(
            {entry.th32ProcessID, entry.th32ParentProcessID, created});
      }
    } while (Process32NextW(snapshot, &entry));
  }
  CloseHandle(snapshot);
  return snapshot_rows;
}

bool AddValidatedProcess(const ProcessRow& row,
                         uint64_t parent_creation_time,
                         uint64_t snapshot_captured_at,
                         std::vector<OwnedProcess>& owned) {
  if (row.creation_time <= parent_creation_time ||
      row.creation_time >= snapshot_captured_at) {
    return false;
  }
  HANDLE process = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION |
                                   PROCESS_TERMINATE | SYNCHRONIZE,
                               FALSE, row.pid);
  if (!process) {
    return false;
  }
  uint64_t current_creation = CreationTime(process);
  if (current_creation == 0 || current_creation != row.creation_time ||
      current_creation <= parent_creation_time ||
      current_creation >= snapshot_captured_at) {
    CloseHandle(process);
    return false;
  }
  owned.emplace_back(row.pid, current_creation, process);
  return true;
}

std::vector<OwnedProcess> OwnedGatewayTree(DWORD app_pid,
                                           uint64_t app_creation_time,
                                           const std::wstring& expected_path) {
  std::vector<OwnedProcess> owned;
  SnapshotRows snapshot = ProcessSnapshot();
  std::vector<size_t> pending;
  if (snapshot.captured_at == 0) {
    return owned;
  }

  for (const ProcessRow& row : snapshot.rows) {
    if (row.parent_pid != app_pid) {
      continue;
    }
    size_t index = owned.size();
    if (!AddValidatedProcess(row, app_creation_time, snapshot.captured_at,
                             owned)) {
      continue;
    }
    if (SamePath(ProcessImagePath(owned[index].handle), expected_path)) {
      pending.push_back(index);
    } else {
      owned.pop_back();
    }
  }

  for (size_t cursor = 0; cursor < pending.size(); ++cursor) {
    DWORD parent_pid = owned[pending[cursor]].pid;
    uint64_t parent_creation_time = owned[pending[cursor]].creation_time;
    for (const ProcessRow& row : snapshot.rows) {
      if (row.parent_pid != parent_pid) {
        continue;
      }
      size_t index = owned.size();
      if (AddValidatedProcess(row, parent_creation_time,
                              snapshot.captured_at, owned)) {
        pending.push_back(index);
      }
    }
  }
  return owned;
}

void TerminateOwnedProcess(HANDLE process) {
  if (!process) {
    return;
  }
  TerminateProcess(process, 1);
  WaitForSingleObject(process, 3000);
}

}  // namespace

void StopOwnedGatewayProcessesOnExit() {
  std::wstring expected = ExpectedGatewayPath();
  if (expected.empty()) {
    return;
  }
  uint64_t app_created = CreationTime(GetCurrentProcess());
  if (app_created == 0) {
    return;
  }
  std::vector<OwnedProcess> owned =
      OwnedGatewayTree(GetCurrentProcessId(), app_created, expected);
  for (auto it = owned.rbegin(); it != owned.rend(); ++it) {
    TerminateOwnedProcess(it->handle);
  }
}
