"""Local terrain library. No process injection, inventory edits or game launching."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import struct
import subprocess
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import webbrowser
import zlib
from tide_trial import Trial, APPROVED_SHA
from packages import CATALOG
from steam_discovery import find_dota_installations, normalize_game_path

GUIDE = 'https://steamcommunity.com/sharedfiles/filedetails/?id=1664733222'
TERRAINS = ['Desert Terrain', 'Immortal Gardens', "Reef’s Edge", 'Emerald Abyss', 'Overgrown Empire', 'Sanctum of the Divine', 'Crownfall', "The King’s New Journey", 'Winter', 'Spring', 'Summer', 'Autumn']
ARCANAS = [('Tidehunter', 'Maw of the Megalodon', 'tidehunter'), ('Vengeful Spirit', 'The Resurrection of Shen', 'vengefulspirit'), ('Skywrath Mage', 'The Devotions of Dragonus', 'skywrath_mage'), ('Razor', 'Voidstorm Asylum', 'razor'), ('Faceless Void', 'Claszian Apostasy', 'faceless_void'), ('Drow Ranger', 'Dread Retribution', 'drow_ranger'), ('Spectre', 'Phantom Advent', 'spectre'), ('Windranger', 'Compass of the Rising Gale', 'windrunner'), ('Queen of Pain', 'The Eminence of Ristul', 'queenofpain'), ('Wraith King', 'The One True King', 'skeleton_king'), ('Earthshaker', 'Planetfall', 'earthshaker'), ('Ogre Magi', 'Flockheart’s Gamble', 'ogre_magi'), ('Rubick', 'The Magus Cypher', 'rubick'), ('Pudge', 'Feast of Abscession', 'pudge'), ('Juggernaut', 'Bladeform Legacy', 'juggernaut'), ('Monkey King', 'Great Sage’s Reckoning', 'monkey_king'), ('Io', 'Benevolent Companion', 'wisp'), ('Zeus', 'Tempest Helm of the Thundergod', 'zuus'), ('Crystal Maiden', 'Frost Avalanche', 'crystal_maiden'), ('Phantom Assassin', 'Manifold Paradox', 'phantom_assassin'), ('Shadow Fiend', 'Demon Eater', 'nevermore'), ('Techies', 'Swine of the Sunken Galley', 'techies'), ('Terrorblade', 'Fractal Horns of Inner Abysm', 'terrorblade'), ('Legion Commander', 'Blades of Voth Domosh', 'legion_commander'), ('Lina', 'Fiery Soul of the Slayer', 'lina')]

SKIN_EXTENSIONS = {'vmdl_c','vtex_c','vmat_c','vpcf_c','vsndevts_c','vsnd_c','vanim_c','vmesh_c','vagrp_c','vseq_c','vsnap_c','vphys_c','vents_c','vwnod_c','vrman_c'}
PORTRAIT_MODELS = {'tidehunter':'models/heroes/tidehunter/tidehunter.vmdl','vengefulspirit':'models/heroes/vengeful/vengeful.vmdl','skywrath_mage':'models/heroes/skywrath_mage/skywrath_mage.vmdl','razor':'models/heroes/razor/razor.vmdl','faceless_void':'models/heroes/faceless_void/faceless_void.vmdl','drow_ranger':'models/heroes/drow_ranger/drow_ranger.vmdl','spectre':'models/heroes/spectre/spectre.vmdl','windrunner':'models/heroes/windrunner/windrunner.vmdl','queenofpain':'models/heroes/queenofpain/queenofpain.vmdl','skeleton_king':'models/heroes/wraith_king/wraith_king.vmdl','earthshaker':'models/heroes/earthshaker/earthshaker.vmdl','ogre_magi':'models/heroes/ogre_magi/ogre_magi.vmdl','rubick':'models/heroes/rubick/rubick.vmdl','pudge':'models/heroes/pudge/pudge.vmdl','juggernaut':'models/heroes/juggernaut/juggernaut.vmdl','monkey_king':'models/heroes/monkey_king/monkey_king.vmdl','wisp':'models/heroes/wisp/wisp.vmdl','zuus':'models/heroes/zeus/zeus.vmdl','crystal_m':'models/heroes/crystal_maiden/crystal_maiden.vmdl','phantom_assassin':'models/heroes/phantom_assassin/phantom_assassin.vmdl','nevermore':'models/heroes/nevermore/nevermore.vmdl','techies':'models/heroes/techies/techies.vmdl','terrorblade':'models/heroes/terrorblade/terrorblade.vmdl','legion_commander':'models/heroes/legion_commander/legion_commander.vmdl','lina':'models/heroes/lina/lina.vmdl','axe':'models/heroes/axe/axe.vmdl'}

def _kv_block_span(data, key):
    import re
    tokens = list(re.finditer(rb'"(?:\\.|[^"\\])*"|[{}]|//[^\r\n]*|/\*.*?\*/', data, re.S))
    significant = [t for t in tokens if not t.group().startswith((b'//',b'/*'))]
    wanted = ('"'+key+'"').encode('utf-8')
    matches = [i for i,t in enumerate(significant) if t.group() == wanted]
    if len(matches) != 1: raise ValueError('Bloco de retrato ausente ou ambíguo.')
    i = matches[0]
    if i+1 >= len(significant) or significant[i+1].group() != b'{': raise ValueError('Bloco de retrato inválido.')
    depth = 0
    for token in significant[i+1:]:
        if token.group() == b'{': depth += 1
        elif token.group() == b'}':
            depth -= 1
            if depth == 0: return significant[i].start(), token.end()
    raise ValueError('Bloco de retrato incompleto.')

def _portrait_is_single_hero_patch(game_path, modified, hero):
    from vpk_lab import index as vpk_index, read_entry
    model = PORTRAIT_MODELS.get(hero)
    if not model: return False
    pak = normalize_game_path(game_path)/'dota/pak01_dir.vpk'
    base, entries = vpk_index(pak)
    original = read_entry(pak,'scripts/npc/portraits.txt',(base,entries))
    try:
        a0,a1 = _kv_block_span(original,model)
        b0,b1 = _kv_block_span(modified,model)
    except (ValueError,UnicodeError): return False
    marker=b'"__ATELIER_HERO_BLOCK__" { }'
    return original[:a0]+marker+original[a1:] == modified[:b0]+marker+modified[b1:]

def digest(path):
    with open(path, 'rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def validate_vpk(path, kind='map', hero=None, game_path=None):
    """Parse a single-file VPK, enforce terrain paths, bounds and entry CRCs."""
    if Path(path).stat().st_size > 512 * 1024 * 1024:
        raise ValueError('Máximo 512 MB por pacote.')
    raw = Path(path).read_bytes()
    known_skin = hashlib.sha256(raw).hexdigest() in {r['sha256'] for r in CATALOG['styles']+CATALOG.get('heroes', [])}
    if len(raw) < 12 or len(raw) > 512 * 1024 * 1024:
        raise ValueError('Tamanho de VPK inválido (máximo 512 MB).')
    magic, version, tree_size = struct.unpack_from('<III', raw)
    if magic != 0x55AA1234 or version not in (1, 2):
        raise ValueError('Não é um VPK Source válido.')
    header = 12 if version == 1 else 28
    if len(raw) < header:
        raise ValueError('Cabeçalho VPK truncado.')
    end = header + tree_size
    if end > len(raw) or tree_size > 16 * 1024 * 1024:
        raise ValueError('Índice VPK inválido.')
    data_end = len(raw) if version == 1 else end + struct.unpack_from('<I', raw, 12)[0]
    if data_end > len(raw):
        raise ValueError('Dados VPK truncados.')
    pos = header
    entries = []
    def string():
        nonlocal pos
        stop = raw.find(b'\0', pos, end)
        if stop < 0:
            raise ValueError('Índice VPK truncado.')
        result = raw[pos:stop].decode('utf-8')
        pos = stop + 1
        return result
    while True:
        ext = string()
        if not ext:
            break
        while True:
            folder = string()
            if not folder:
                break
            while True:
                name = string()
                if not name:
                    break
                if pos + 18 > end:
                    raise ValueError('Entrada VPK truncada.')
                crc, preload, archive, offset, length, terminator = struct.unpack_from('<IHHIIH', raw, pos)
                pos += 18
                resource = f'{folder}/{name}.{ext}'
                if kind == 'skin':
                    allowed = ext in SKIN_EXTENSIONS and not resource.startswith(('scripts/','cfg/','bin/','resource/','panorama/layout/','panorama/scripts/','maps/'))
                    if resource == 'scripts/npc/portraits.txt':
                        payload = raw[pos:pos+preload] + raw[end+offset:end+offset+length]
                        allowed = known_skin or bool(hero and game_path and _portrait_is_single_hero_patch(game_path,payload,hero))
                else:
                    allowed = resource.startswith(('maps/dota/', 'maps/dota_')) or (folder == 'maps' and name == 'dota')
                if not allowed or '..' in resource or '\\' in resource or ':' in resource or resource.startswith('/'):
                    raise ValueError(f'Recurso fora do mapa: {resource}')
                if ext not in {'gnv', 'vhcg', 'vgrass', 'trm', 'vmap_c', 'vwrld_c', 'vwnod_c', 'vphys_c', 'vmat_c', 'vtex_c', 'vmdl_c', 'vmesh_c', 'vpcf_c', 'vsnd_c', 'vrman_c', 'vents_c', 'vvis_c', 'vanim_c', 'vagrp_c', 'vseq_c', 'nav', 'nav_c'} and not (kind == 'skin' and ((ext in {'vsndevts_c','vsnap_c'} and (resource.startswith('soundevents/') or known_skin)) or (resource == 'scripts/npc/portraits.txt' and allowed))):
                    raise ValueError(f'Tipo de recurso não permitido: {ext}')
                if archive != 0x7fff or terminator != 0xffff or pos + preload > end or end + offset + length > data_end:
                    raise ValueError('Pacote externo, truncado ou inválido.')
                payload = raw[pos:pos+preload] + raw[end+offset:end+offset+length]
                pos += preload
                if zlib.crc32(payload) & 0xffffffff != crc:
                    raise ValueError(f'CRC incorreto: {resource}')
                entries.append(resource)
                if len(entries) > 50000:
                    raise ValueError('Pacote com recursos demais.')
    if not entries or pos != end:
        raise ValueError('Índice vazio ou inconsistente.')
    return entries

def game_closed():
    result = subprocess.run(['tasklist', '/FO', 'CSV', '/NH'], capture_output=True, text=True, creationflags=0x08000000, check=True)
    if '"dota2.exe"' in result.stdout.lower():
        raise ValueError('Feche o Dota 2 antes de trocar arquivos.')

def atomic_copy(source, destination):
    destination = Path(destination)
    temporary = destination.with_name(destination.name + '.manager-tmp')
    if temporary.exists():
        raise ValueError('Arquivo temporário existente. Confira a pasta antes de continuar.')
    try:
        shutil.copyfile(source, temporary)
        if digest(source) != digest(temporary):
            raise ValueError('A cópia não passou na verificação SHA-256.')
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)

class Library:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.statefile = self.root / 'state.json'
        self.state = json.loads(self.statefile.read_text('utf-8')) if self.statefile.exists() else {'items': {}, 'sessions': {}}
        self.state.setdefault('skins', {})
        self.state.setdefault('imported_skins', {})
        self.state.setdefault('generated_skins', {})
        self._source_hash_cache = {}
        previous_game_path = self.state.get('game_path')
        configured = previous_game_path
        if not configured and self.state.get('target'):
            try: configured = str(normalize_game_path(Path(self.state['target']).parents[1]))
            except (OSError,ValueError): configured = None
        if configured:
            try: configured = str(normalize_game_path(configured))
            except (OSError,ValueError): configured = None
        if not configured:
            detected = find_dota_installations()
            configured = str(detected[0]) if detected else ''
        self.state['game_path'] = configured
        if configured and configured != previous_game_path: self.save()
    def save(self):
        temp = self.statefile.with_suffix('.tmp')
        temp.write_text(json.dumps(self.state, indent=2, ensure_ascii=False), 'utf-8')
        os.replace(temp, self.statefile)
    def target(self):
        configured = Path(self.state['target']).absolute()
        for part in [configured, *configured.parents]:
            if part.exists() and part.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                raise ValueError('Pastas redirecionadas não são permitidas.')
        folder = configured.resolve()
        if folder.name != 'maps' or folder.parent.name != 'dota_brazilian' or folder.parent.parent.name != 'game':
            raise ValueError('Selecione somente game\\dota_brazilian\\maps.')
        if not folder.is_dir() or folder.is_symlink() or folder.parent.is_symlink():
            raise ValueError('Pasta ausente ou redirecionada.')
        target = folder / 'dota.vpk'
        if target.exists() and target.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise ValueError('Arquivo redirecionado não permitido.')
        return target
    def import_map(self, name, source):
        entries = validate_vpk(source)
        key = digest(source)
        destination = self.root / (key + '.vpk')
        if not destination.exists():
            atomic_copy(source, destination)
        self.state['items'][name] = {'hash': key, 'entries': len(entries)}
        self.save()
    def activate(self, name):
        raise ValueError('Instalação no jogo bloqueada nesta edição de inspeção. Não há garantia de aceitação pela Steam.')
    def restore(self):
        raise ValueError('Esta edição não escreve na instalação do jogo. Backups anteriores continuam preservados na biblioteca.')
    def import_skin(self, hero, source):
        candidates = CATALOG['styles'] if hero == 'tidehunter' else [h for h in CATALOG.get('heroes',[]) if h['hero']==hero]
        if not candidates: raise ValueError('Herói inválido.')
        return self.import_skin_variant(hero,candidates[0]['id'],source)

    def import_skin_variant(self, hero, skin_id, source):
        candidates = CATALOG['styles'] if hero == 'tidehunter' else [h for h in CATALOG.get('heroes',[]) if h['hero']==hero]
        template = next((row for row in candidates if row['id']==skin_id),None)
        if template is None: raise ValueError('Variante de visual inválida.')
        game_path = self.state.get('game_path')
        if not game_path: raise ValueError('Selecione a instalação do Dota antes de importar um pacote.')
        entries = validate_vpk(source,'skin',hero=hero,game_path=game_path)
        sha = digest(source)
        destination = self.root/'skins'/(sha+'.vpk')
        destination.parent.mkdir(parents=True,exist_ok=True)
        if not destination.exists():
            atomic_copy(source, destination)
        report = {k:v for k,v in template.items() if k not in ('sha256','resources','file')}
        hero_name='Tidehunter' if hero=='tidehunter' else next((h['hero_name'] for h in CATALOG.get('heroes',[]) if h['hero']==hero),hero)
        report.update({'hero':hero,'hero_name':hero_name,'id':skin_id,'sha256':sha,'resources':len(entries),
                       'local_file':str(destination.relative_to(self.root)),
                       'source_filename':Path(source).name,
                       'status':'Pacote local importado e validado estruturalmente; compatibilidade visual ainda requer conferência no jogo.'})
        self.state['imported_skins'][f'{hero}:{skin_id}'] = report
        self.save()
        return report

    def imported_skin(self, hero, skin_id):
        item=self.state.get('imported_skins',{}).get(f'{hero}:{skin_id}')
        if not item:return None
        key=item.get('sha256','')
        if len(key)!=64 or any(c not in '0123456789abcdef' for c in key):
            raise ValueError('Hash do pacote local inválido.')
        expected=f"skins/{key}.vpk"
        if item.get('local_file')!=expected:raise ValueError('Registro do pacote local inválido.')
        path=self.root/expected
        if not path.is_file() or digest(path)!=item['sha256']:
            raise ValueError('O pacote local foi alterado. Importe o VPK novamente.')
        return {**item,'package_path':str(path)}

    def register_generated_skin(self, report):
        hero, skin_id = report.get('hero'), report.get('id')
        candidates = CATALOG['styles'] if hero == 'tidehunter' else [h for h in CATALOG.get('heroes', []) if h['hero'] == hero]
        template = next((row for row in candidates if row['id'] == skin_id), None)
        if template is None: raise ValueError('A arcana não pertence ao catálogo local.')
        key = report.get('sha256', '')
        if len(key) != 64 or any(c not in '0123456789abcdef' for c in key): raise ValueError('Hash do pacote gerado inválido.')
        expected = f'skins/{key}.vpk'
        if report.get('local_file') != expected: raise ValueError('Caminho do pacote gerado inválido.')
        game_path = str(normalize_game_path(self.state.get('game_path', '')))
        if report.get('game_path') != game_path: raise ValueError('O pacote foi montado para outra instalação do Dota.')
        path = self.root / expected
        if not path.is_file() or digest(path) != key: raise ValueError('O pacote montado não passou na conferência local.')
        hero_name = 'Tidehunter' if hero == 'tidehunter' else template['hero_name']
        stored = {**{k: v for k, v in template.items() if k not in ('sha256', 'resources', 'file')}, **report,
                  'hero': hero, 'hero_name': hero_name, 'name': template['name'], 'image': template['image'],
                  'generated': True, 'package_path': str(path)}
        self.state['generated_skins'][f'{hero}:{skin_id}'] = stored
        self.save()
        return stored

    def generated_skin(self, hero, skin_id):
        item = self.state.get('generated_skins', {}).get(f'{hero}:{skin_id}')
        if not item: return None
        key = item.get('sha256', '')
        if len(key) != 64 or any(c not in '0123456789abcdef' for c in key):
            raise ValueError('Hash do pacote automático inválido.')
        expected = f"skins/{key}.vpk"
        if item.get('hero') != hero or item.get('id') != skin_id or item.get('local_file') != expected:
            raise ValueError('Registro do pacote automático inválido.')
        if item.get('game_path') != str(normalize_game_path(self.state.get('game_path', ''))):
            return None
        sources = item.get('official_sources', {})
        if not sources or any(p not in ('dota/pak01_dir.vpk', 'core/pak01_dir.vpk') for p in sources):
            return None
        for relative, expected_hash in sources.items():
            source = Path(self.state['game_path']) / relative
            if not source.is_file(): return None
            stat_result = source.stat()
            stamp = (stat_result.st_size, stat_result.st_mtime_ns, stat_result.st_ctime_ns)
            cached = self._source_hash_cache.get(str(source))
            if cached is None or cached[0] != stamp:
                cached = (stamp, digest(source))
                self._source_hash_cache[str(source)] = cached
            if cached[1] != expected_hash: return None
        path = self.root / expected
        if not path.is_file() or digest(path) != item['sha256']:
            raise ValueError('O pacote automático foi alterado. Baixe e prepare novamente.')
        return {**item, 'package_path': str(path)}

    def set_game_path(self, path):
        self.state['game_path']=str(normalize_game_path(path))
        self.save()

from desktop_ui import App

if __name__ == '__main__':
    from app_lock import AppLock
    instance_lock = AppLock()
    root = tk.Tk()
    try:
        if not instance_lock.acquire():
            root.withdraw()
            messagebox.showinfo('Dota Atelier', 'O Dota Atelier já está aberto nesta sessão do Windows.', parent=root)
            root.destroy()
            raise SystemExit(0)
        library = Library(Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'DotaAtelier')
        if not library.state.get('game_path'):
            root.withdraw()
            messagebox.showinfo('Dota Atelier','Não encontrei o Dota automaticamente. Selecione a pasta game da instalação.',parent=root)
            selected = filedialog.askdirectory(title='Selecione a pasta game do Dota 2',parent=root)
            if not selected:
                root.destroy()
                raise SystemExit(0)
            library.set_game_path(selected)
        root.deiconify()
        app = App(root, library)
        root.mainloop()
    except Exception as exc:
        messagebox.showerror('Dota Atelier', str(exc))
        root.destroy()
