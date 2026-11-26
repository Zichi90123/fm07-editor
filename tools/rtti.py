"""Mappa vtable -> nome classe (RTTI MSVC, 32 bit) di un eseguibile PE.

Uso (con Python normale, anche fuori da Windows):
    python rtti.py "C:/.../Football Manager 2007/fm.exe" vt07.json
Scrive {"0xVTABLE": ["nome classe", offset del sotto-oggetto]}: con due versioni del gioco
si trovano le vtable corrispondenti cercando lo stesso nome e offset (vedi MAPPA.md).
"""
import json
import re
import struct
import sys


def load(path):
    """Immagine del PE mappata in memoria (sezioni ai loro indirizzi virtuali) e base."""
    d = open(path, 'rb').read()
    pe = struct.unpack_from('<I', d, 0x3C)[0]
    nsec = struct.unpack_from('<H', d, pe + 6)[0]
    optsz = struct.unpack_from('<H', d, pe + 20)[0]
    base = struct.unpack_from('<I', d, pe + 24 + 28)[0]
    secs = []
    o = pe + 24 + optsz
    for _ in range(nsec):
        name = d[o:o + 8].rstrip(b'\0').decode(errors='replace')
        vsz, va, rsz, rptr = struct.unpack_from('<IIII', d, o + 8)
        secs.append((name, va, vsz, rptr, rsz))
        o += 40
    top = max(va + max(vsz, rsz) for _, va, vsz, _, rsz in secs)
    img = bytearray(top)
    img[:0x1000] = d[:0x1000]
    for _, va, vsz, rptr, rsz in secs:
        img[va:va + rsz] = d[rptr:rptr + rsz]
    return bytes(img), base, secs


def vtables(path):
    img, base, _ = load(path)
    n = len(img)
    # type descriptor: ptr vtable, spare, nome ".?AV...@@"
    tds = {}
    for m in re.finditer(rb'\.\?A[VU][^\0]{1,200}@@\0', img):
        tds[m.start() - 8 + base] = m.group()[:-1].decode(errors='replace')
    # Complete Object Locator: signature 0, offset, cdOffset, pTypeDescriptor, pClassHierarchy
    arr = memoryview(img)[:n - n % 4].cast('I')
    cols = {}
    for i in range(0, len(arr) - 5):
        if arr[i] == 0 and arr[i + 3] in tds:
            cols[i * 4 + base] = (tds[arr[i + 3]], arr[i + 1])
    # la vtable segue il puntatore al COL, e il suo primo metodo sta nel codice
    out = {}
    for i in range(len(arr) - 1):
        if arr[i] in cols:
            f = arr[i + 1] - base
            if 0x1000 <= f < n:
                out[(i + 1) * 4 + base] = cols[arr[i]]
    return out, base


if __name__ == '__main__':
    out, base = vtables(sys.argv[1])
    print(len(out), 'vtable, base', hex(base), file=sys.stderr)
    with open(sys.argv[2], 'w') as fh:
        json.dump({f'0x{k:08X}': v for k, v in out.items()}, fh, indent=0)
