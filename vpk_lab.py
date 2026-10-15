"""Read-only inspection and deterministic VPK repacking for a cosmetic test.

Source 2 RERL layout reference: ValveResourceFormat (MIT),
https://github.com/ValveResourceFormat/ValveResourceFormat
No compiled resource is executed or rewritten by this module.
"""
import collections
import struct
import zlib
from pathlib import Path

def read_entry(path, resource, cached_index=None):
    """Read a CRC-checked resource from inline or numbered game VPK volumes."""
    path = Path(path)
    base, entries = cached_index if cached_index is not None else index(path)
    crc, archive, offset, length, preload = entries[resource]
    volume = path if archive == 0x7fff else path.with_name(path.name.removesuffix('_dir.vpk')+f'_{archive:03}.vpk')
    with volume.open('rb') as stream:
        stream.seek(offset+(base if archive == 0x7fff else 0))
        data = preload+stream.read(length)
    if len(data) != len(preload)+length or zlib.crc32(data)&0xffffffff != crc:
        raise ValueError('Recurso truncado ou CRC incorreto: '+resource)
    return data


def index(path):
    with Path(path).open('rb') as stream:
        header = stream.read(12)
        magic, version, size = struct.unpack('<III', header)
        if magic != 0x55aa1234 or version not in (1, 2) or size > 64*1024*1024:
            raise ValueError('Cabeçalho VPK inválido.')
        start = 28 if version == 2 else 12
        stream.seek(start)
        tree = stream.read(size)
    pos = 0
    out = {}
    def string():
        nonlocal pos
        end = tree.index(0, pos)
        value = tree[pos:end].decode('utf-8')
        pos = end+1
        return value
    while True:
        ext = string()
        if not ext: break
        while True:
            folder = string()
            if not folder: break
            while True:
                name = string()
                if not name: break
                crc, preload, archive, offset, length, end = struct.unpack_from('<IHHIIH', tree, pos)
                pos += 18
                resource = ('' if folder == ' ' else folder+'/')+name+'.'+ext
                if end != 0xffff or pos+preload > len(tree) or resource in out:
                    raise ValueError('Entrada inválida ou duplicada.')
                out[resource] = (crc, archive, offset, length, tree[pos:pos+preload])
                pos += preload
    if pos != size: raise ValueError('Índice inconsistente.')
    return start+size, out


def read_single(path):
    base, entries = index(path)
    result = {}
    with Path(path).open('rb') as stream:
        for name, (crc, archive, offset, length, preload) in entries.items():
            if archive != 0x7fff: raise ValueError('VPK multipartes não suportado aqui.')
            stream.seek(base+offset)
            payload = preload+stream.read(length)
            if len(payload) != len(preload)+length or zlib.crc32(payload)&0xffffffff != crc:
                raise ValueError('CRC inválido: '+name)
            result[name] = payload
    return result


def write_single(path, entries, deduplicate=False):
    groups = collections.defaultdict(lambda: collections.defaultdict(dict))
    for resource, payload in entries.items():
        if '\\' in resource or ':' in resource or any(x in ('', '.', '..') for x in resource.split('/')):
            raise ValueError('Caminho inválido.')
        folder, name = resource.rsplit('/', 1)
        stem, ext = name.rsplit('.', 1)
        groups[ext][folder][stem] = payload
    tree, data = bytearray(), bytearray()
    locations = {}
    def string(s): tree.extend(s.encode()+b'\0')
    for ext in sorted(groups):
        string(ext)
        for folder in sorted(groups[ext]):
            string(folder)
            for name, payload in sorted(groups[ext][folder].items()):
                string(name)
                offset = locations.get(payload) if deduplicate else None
                if offset is None:
                    offset = len(data)
                    data.extend(payload)
                    if deduplicate: locations[payload] = offset
                tree.extend(struct.pack('<IHHIIH', zlib.crc32(payload)&0xffffffff, 0, 0x7fff, offset, len(payload), 0xffff))
            string('')
        string('')
    string('')
    Path(path).write_bytes(struct.pack('<III', 0x55aa1234, 1, len(tree))+tree+data)
    if read_single(path) != entries: raise ValueError('Reempacotamento inconsistente.')


def references(payload):
    """Read only the external-reference block, not executable data or scripts."""
    if len(payload) < 16: raise ValueError('Recurso truncado.')
    _, header, _, offset, count = struct.unpack_from('<IHHII', payload)
    if header != 12 or count > 4096 or 8+offset+12*count > len(payload):
        raise ValueError('Recurso Source 2 inválido.')
    refs = []
    for i in range(count):
        entry = 8+offset+i*12
        tag, relative, size = struct.unpack_from('<4sII', payload, entry)
        block = entry+4+relative
        if block+size > len(payload): raise ValueError('Bloco truncado.')
        if tag != b'RERL': continue
        array, length = struct.unpack_from('<II', payload, block)
        if length > 10000: raise ValueError('Referências demais.')
        for n in range(length):
            field = block+array+n*16+8
            name = field+struct.unpack_from('<i', payload, field)[0]
            if not block <= name < block+size: raise ValueError('Referência inválida.')
            end = payload.index(0, name, block+size)
            refs.append(payload[name:end].decode('utf-8'))
    return refs
