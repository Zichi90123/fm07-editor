"""Accesso alla memoria di un processo Windows (fm.exe) tramite ctypes.

Nessuna dipendenza esterna: usa direttamente le API di kernel32.
"""
import ctypes
import ctypes.wintypes as wt
import struct
import sys

if sys.platform != "win32":
    raise RuntimeError("Questo editor funziona solo su Windows")

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

PROCESS_VM_READ = 0x0010
PROCESS_VM_WRITE = 0x0020
PROCESS_VM_OPERATION = 0x0008
PROCESS_QUERY_INFORMATION = 0x0400
STILL_ACTIVE = 259

MEM_COMMIT = 0x1000
PAGE_GUARD = 0x100
WRITABLE = {0x04, 0x08, 0x40, 0x80}  # READWRITE, WRITECOPY, EXECUTE_READWRITE, EXECUTE_WRITECOPY

TH32CS_SNAPPROCESS = 0x2
TH32CS_SNAPMODULE = 0x8
TH32CS_SNAPMODULE32 = 0x10
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

# tipo -> (formato struct, dtype numpy, dimensione)
TYPES = {
    "byte":   ("<B", "<u1", 1),
    "int16":  ("<h", "<i2", 2),
    "int32":  ("<i", "<i4", 4),
    "int64":  ("<q", "<i8", 8),
    "float":  ("<f", "<f4", 4),
    "double": ("<d", "<f8", 8),
}


class MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_void_p),
        ("AllocationBase", ctypes.c_void_p),
        ("AllocationProtect", wt.DWORD),
        ("RegionSize", ctypes.c_size_t),
        ("State", wt.DWORD),
        ("Protect", wt.DWORD),
        ("Type", wt.DWORD),
    ]


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wt.DWORD),
        ("cntUsage", wt.DWORD),
        ("th32ProcessID", wt.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wt.DWORD),
        ("cntThreads", wt.DWORD),
        ("th32ParentProcessID", wt.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wt.DWORD),
        ("szExeFile", ctypes.c_wchar * 260),
    ]


class MODULEENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wt.DWORD),
        ("th32ModuleID", wt.DWORD),
        ("th32ProcessID", wt.DWORD),
        ("GlblcntUsage", wt.DWORD),
        ("ProccntUsage", wt.DWORD),
        ("modBaseAddr", ctypes.c_void_p),
        ("modBaseSize", wt.DWORD),
        ("hModule", wt.HMODULE),
        ("szModule", ctypes.c_wchar * 256),
        ("szExePath", ctypes.c_wchar * 260),
    ]


kernel32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
kernel32.OpenProcess.restype = wt.HANDLE
kernel32.CloseHandle.argtypes = [wt.HANDLE]
kernel32.CloseHandle.restype = wt.BOOL
kernel32.ReadProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
kernel32.ReadProcessMemory.restype = wt.BOOL
kernel32.WriteProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
kernel32.WriteProcessMemory.restype = wt.BOOL
kernel32.VirtualQueryEx.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.POINTER(MEMORY_BASIC_INFORMATION), ctypes.c_size_t]
kernel32.VirtualQueryEx.restype = ctypes.c_size_t
kernel32.GetExitCodeProcess.argtypes = [wt.HANDLE, ctypes.POINTER(wt.DWORD)]
kernel32.GetExitCodeProcess.restype = wt.BOOL
kernel32.CreateToolhelp32Snapshot.argtypes = [wt.DWORD, wt.DWORD]
kernel32.CreateToolhelp32Snapshot.restype = wt.HANDLE
kernel32.Process32FirstW.argtypes = [wt.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
kernel32.Process32FirstW.restype = wt.BOOL
kernel32.Process32NextW.argtypes = [wt.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
kernel32.Process32NextW.restype = wt.BOOL
kernel32.Module32FirstW.argtypes = [wt.HANDLE, ctypes.POINTER(MODULEENTRY32W)]
kernel32.Module32FirstW.restype = wt.BOOL
kernel32.Module32NextW.argtypes = [wt.HANDLE, ctypes.POINTER(MODULEENTRY32W)]
kernel32.Module32NextW.restype = wt.BOOL


def find_pid(name="fm.exe"):
    snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if not snap or snap == INVALID_HANDLE_VALUE:
        raise OSError(ctypes.get_last_error(), "CreateToolhelp32Snapshot fallita")
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        ok = kernel32.Process32FirstW(snap, ctypes.byref(entry))
        while ok:
            if entry.szExeFile.lower() == name.lower():
                return entry.th32ProcessID
            ok = kernel32.Process32NextW(snap, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snap)
    return None


class Process:
    def __init__(self, pid, name):
        access = PROCESS_VM_READ | PROCESS_VM_WRITE | PROCESS_VM_OPERATION | PROCESS_QUERY_INFORMATION
        handle = kernel32.OpenProcess(access, False, pid)
        if not handle:
            err = ctypes.get_last_error()
            if err == 5:
                raise PermissionError(
                    "Accesso negato a fm.exe: se il gioco è avviato come amministratore, "
                    "avvia anche l'editor come amministratore (o togli l'admin al gioco)."
                )
            raise OSError(err, f"OpenProcess fallita (errore {err})")
        self.handle = handle
        self.pid = pid
        self.name = name

    @classmethod
    def attach(cls, name="fm.exe"):
        pid = find_pid(name)
        if pid is None:
            raise LookupError(f"{name} non è in esecuzione: apri FM2007 e carica la partita")
        return cls(pid, name)

    def close(self):
        if self.handle:
            kernel32.CloseHandle(self.handle)
            self.handle = None

    def is_alive(self):
        if not self.handle:
            return False
        code = wt.DWORD()
        if not kernel32.GetExitCodeProcess(self.handle, ctypes.byref(code)):
            return False
        return code.value == STILL_ACTIVE

    # --- regioni -----------------------------------------------------------
    def regions(self, writable_only=True):
        """Restituisce [(base, size)] delle regioni di memoria committed."""
        out = []
        mbi = MEMORY_BASIC_INFORMATION()
        addr = 0
        limit = 0x7FFFFFFF0000
        while addr < limit:
            if not kernel32.VirtualQueryEx(self.handle, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)):
                break
            base = mbi.BaseAddress or 0
            size = mbi.RegionSize
            if size == 0:
                break
            if (mbi.State == MEM_COMMIT and not (mbi.Protect & PAGE_GUARD)
                    and (not writable_only or (mbi.Protect & 0xFF) in WRITABLE)):
                out.append((base, size))
            addr = base + size
        return out

    # --- lettura / scrittura ------------------------------------------------
    def read(self, address, size):
        buf = ctypes.create_string_buffer(size)
        got = ctypes.c_size_t(0)
        ok = kernel32.ReadProcessMemory(self.handle, ctypes.c_void_p(address), buf, size, ctypes.byref(got))
        if not ok or got.value != size:
            return None
        return buf.raw

    def write(self, address, data):
        got = ctypes.c_size_t(0)
        ok = kernel32.WriteProcessMemory(self.handle, ctypes.c_void_p(address), data, len(data), ctypes.byref(got))
        return bool(ok) and got.value == len(data)

    def read_value(self, address, vtype):
        fmt, _, size = TYPES[vtype]
        data = self.read(address, size)
        if data is None:
            return None
        return struct.unpack(fmt, data)[0]

    def write_value(self, address, vtype, value):
        fmt, _, _ = TYPES[vtype]
        if vtype in ("float", "double"):
            value = float(value)
        else:
            value = int(value)
        return self.write(address, struct.pack(fmt, value))

    def read_pointer32(self, address):
        """FM2007 è un processo a 32 bit: i puntatori sono di 4 byte."""
        data = self.read(address, 4)
        return None if data is None else struct.unpack("<I", data)[0]

    def modules(self):
        """Restituisce [(nome, base, dimensione)] dei moduli caricati (exe e dll)."""
        snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32, self.pid)
        if not snap or snap == INVALID_HANDLE_VALUE:
            return []
        out = []
        try:
            entry = MODULEENTRY32W()
            entry.dwSize = ctypes.sizeof(MODULEENTRY32W)
            ok = kernel32.Module32FirstW(snap, ctypes.byref(entry))
            while ok:
                out.append((entry.szModule, entry.modBaseAddr or 0, entry.modBaseSize))
                ok = kernel32.Module32NextW(snap, ctypes.byref(entry))
        finally:
            kernel32.CloseHandle(snap)
        return out

    def module_base(self, module_name=None):
        module_name = (module_name or self.name).lower()
        for name, base, size in self.modules():
            if name.lower() == module_name:
                return base, size
        return None
