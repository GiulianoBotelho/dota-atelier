"""Shared, reversible audio mount for cosmetic hero packages and one terrain."""
import base64
import copy
import json
from pathlib import Path
import uuid
from packages import CATALOG
from tide_trial import AUDIO, PROTECTED, KNOWN_PACKAGES, clean_path, closed, put, sha

# Stable allocation: catalog sorting or new heroes must never relocate an active slot.
HERO_SLOT_ORDER = ('vengefulspirit', 'skywrath_mage', 'razor', 'faceless_void',
    'drow_ranger', 'spectre', 'windrunner', 'queenofpain', 'skeleton_king',
    'earthshaker', 'ogre_magi', 'rubick', 'pudge', 'juggernaut', 'monkey_king',
    'wisp', 'zuus', 'crystal_maiden', 'phantom_assassin', 'nevermore', 'techies',
    'terrorblade', 'legion_commander', 'lina', 'axe')

class Session:
    def __init__(self, game, library):
        self.game, self.library = clean_path(game), clean_path(library)
        self.library.mkdir(parents=True, exist_ok=True)
        self.journal = self.library/'cosmetic-session.json'
        self.legacy = self.library/'tidehunter-trial.json'
        self.boot = clean_path(self.game/'dota/cfg/boot.vcfg')
        self.cache = {}

    def digest(self, path):
        path = clean_path(path)
        if not path.exists(): return None
        stat = path.stat()
        fingerprint = (stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
        old = self.cache.get(str(path))
        if old and old[0] == fingerprint: return old[1]
        value = sha(path.read_bytes())
        self.cache[str(path)] = (fingerprint, value)
        return value

    def protected(self): return {p:self.digest(self.game/p) for p in PROTECTED}

    def verify_sources(self, item):
        if 'native_map' in item:
            source = self.game/'dota/maps'/(item['native_map']+'.vpk')
            default = self.game/'dota/maps/dota.vpk'
            if self.digest(source) != item['original_game_sha256'] or self.digest(default) != item['original_default_sha256']:
                raise ValueError('O Dota atualizou os arquivos do mapa. Atualize os pacotes do Atelier antes de ativar este terreno.')
        for relative, expected in item.get('official_sources', {}).items():
            if relative not in ('dota/pak01_dir.vpk', 'core/pak01_dir.vpk'):
                raise ValueError('Origem oficial inválida no registro da arcana.')
            path = self.game/relative
            if self.digest(path) != expected:
                raise ValueError('Os arquivos oficiais do Dota mudaram desde que esta arcana foi preparada. Baixe e prepare novamente.')

    def save(self, record):
        put(self.journal, json.dumps(record, ensure_ascii=False, indent=2).encode(), self.digest(self.journal))

    def read(self):
        if self.journal.exists():
            record = json.loads(self.journal.read_text('utf-8'))
        elif self.legacy.exists():
            old = json.loads(self.legacy.read_text('utf-8'))
            if old['package_sha256'] not in KNOWN_PACKAGES: raise ValueError('Registro anterior desconhecido.')
            record = {'game':old['game'], 'language':old['audio_after'], 'boot_before':old['boot_before'], 'boot_after':old['boot_after'], 'protected':old['protected_before'], 'originals':{'skin:tidehunter':None}, 'slots':{'skin:tidehunter':{'id':'megalodon' if old['package_sha256']==CATALOG['styles'][0]['sha256'] else 'legacy', 'name':'Maw of the Megalodon', 'sha256':old['package_sha256']}}, 'legacy_migration':True}
        else: return None
        if record['game'] != str(self.game) or record['language'] not in ('russian','koreana','schinese'):
            raise ValueError('Registro de instalação inválido.')
        return record

    def target(self, slot, record):
        root = self.game/('dota_'+record['language'])
        if slot == 'map': return clean_path(root/'maps/dota.vpk')
        if slot == 'skin:tidehunter': return clean_path(root/'pak98_dir.vpk')
        hero = slot.removeprefix('skin:')
        heroes = HERO_SLOT_ORDER
        if not slot.startswith('skin:') or hero not in heroes: raise ValueError('Slot desconhecido.')
        return clean_path(root/f'pak{60+heroes.index(hero):02}_dir.vpk')

    def check(self, record):
        if record.get('pending'): raise ValueError('Operação interrompida. Feche o Dota e use Recuperar sessão.')
        if self.boot.read_bytes() != base64.b64decode(record['boot_after']):
            raise ValueError('Configuração de áudio alterada fora do aplicativo.')
        for slot,item in record['slots'].items():
            if self.digest(self.target(slot, record)) != item['sha256']:
                raise ValueError('Pacote alterado fora do aplicativo: '+slot)

    def state(self):
        try:
            record = self.read()
            if record: self.check(record)
            return {'slots':record['slots'] if record else {}, 'conflict':None}
        except (OSError, ValueError, KeyError) as exc:
            return {'slots':{}, 'conflict':str(exc)}

    def baseline(self):
        before = self.boot.read_bytes()
        matches = list(AUDIO.finditer(before))
        if len(matches) != 1: raise ValueError('Idioma de áudio ausente ou ambíguo.')
        audio = matches[0].group(2).decode('ascii')
        if audio not in ('english','russian','koreana','schinese'): raise ValueError('Idioma de áudio não suportado para esta camada.')
        language = 'russian' if audio == 'english' else audio
        root = clean_path(self.game/('dota_'+language))
        if not (root/'gameinfo.gi').is_file(): raise ValueError('Camada oficial de idioma ausente.')
        if audio == 'english' and list(root.glob('pak01*.vpk')): raise ValueError('Há um pacote de voz russo instalado. Selecione uma camada sem pacote de voz antes da ativação.')
        after = AUDIO.sub(lambda m:m.group(1)+language.encode()+m.group(3), before)
        return {'game':str(self.game), 'language':language, 'boot_before':base64.b64encode(before).decode(), 'boot_after':base64.b64encode(after).decode(), 'protected':self.protected(), 'originals':{}, 'slots':{}}

    def backup(self, payload):
        if payload is None: return None
        key = sha(payload)
        path = clean_path(self.library/'backups'/key)
        path.parent.mkdir(exist_ok=True)
        if not path.exists(): put(path,payload,None)
        elif self.digest(path) != key: raise ValueError('Backup inconsistente.')
        return key

    def restore_bytes(self, key):
        if key is None: return None
        if len(key)!=64 or any(c not in '0123456789abcdef' for c in key): raise ValueError('Backup inválido.')
        data = clean_path(self.library/'backups'/key).read_bytes()
        if sha(data) != key: raise ValueError('Backup corrompido.')
        return data

    def write(self, path, payload, expected):
        if payload is None:
            if self.digest(path) != expected: raise ValueError('Arquivo alterado durante a operação.')
            if expected is not None: path.unlink()
        else:
            clean_path(path.parent).mkdir(parents=True,exist_ok=True)
            put(path,payload,expected)

    def recover(self):
        closed()
        record = self.read()
        if not record or not record.get('pending'): return
        pending = record['pending']
        for change in pending['changes']:
            path = self.boot if change['slot']=='boot' else self.target(change['slot'],record)
            if self.digest(path) not in (change['before'],change['after']): raise ValueError('Arquivo externo impede recuperação automática.')
        for change in reversed(pending['changes']):
            path = self.boot if change['slot']=='boot' else self.target(change['slot'],record)
            self.write(path,self.restore_bytes(change['before']),self.digest(path))
        stable = pending['stable']
        if stable is not None: self.save(stable)
        else: self.journal.unlink()

    def change(self, slot, item=None, package=None):
        closed()
        protected_now=self.protected()
        stable = self.read()
        if stable and stable.get('pending'):
            self.recover()
            stable = self.read()
        if stable: self.check(stable)
        record = copy.deepcopy(stable) if stable else self.baseline()
        if item is not None:
            if slot=='map':
                from terrain_updater import TerrainUpdater
                updater=TerrainUpdater(self.game,self.library)
                approved=updater.catalog()
                accepted=any(item == candidate for candidate in approved)
            else:
                hero=slot.removeprefix('skin:')
                statefile=self.library/'state.json'
                state=json.loads(statefile.read_text('utf-8')) if statefile.exists() else {}
                imported=state.get('imported_skins',{}).get(f"{hero}:{item.get('id')}")
                generated=state.get('generated_skins',{}).get(f"{hero}:{item.get('id')}")
                pinned=CATALOG['styles'] if hero=='tidehunter' else [h for h in CATALOG.get('heroes',[]) if h['hero']==hero]
                accepted=any(all(item.get(key)==value for key,value in candidate.items()) for candidate in pinned)
                if imported and imported.get('sha256')==item.get('sha256') and imported.get('name')==item.get('name') and imported.get('hero')==hero:
                    accepted=True
                    key=imported.get('sha256','')
                    if len(key)!=64 or any(c not in '0123456789abcdef' for c in key) or imported.get('local_file')!=f'skins/{key}.vpk':
                        raise ValueError('Registro do pacote local inválido.')
                    imported_path=clean_path(self.library/'skins'/(key+'.vpk'))
                    if clean_path(package)!=imported_path: raise ValueError('Pacote local não corresponde à importação selecionada.')
                if generated and generated.get('sha256')==item.get('sha256') and generated.get('name')==item.get('name') and generated.get('hero')==hero:
                    accepted=True
                    key=generated.get('sha256','')
                    if (len(key)!=64 or any(c not in '0123456789abcdef' for c in key)
                            or generated.get('local_file')!=f'skins/{key}.vpk'
                            or generated.get('id')!=item.get('id')):
                        raise ValueError('Registro do pacote automático inválido.')
                    generated_path=clean_path(self.library/'skins'/(key+'.vpk'))
                    if clean_path(package)!=generated_path: raise ValueError('Pacote local não corresponde ao pacote montado.')
            if not accepted: raise ValueError('Pacote não pertence ao catálogo ou à biblioteca local.')
            self.verify_sources(item)
            if slot=='map' and item.get('generated'):
                updater.validate_generated(item,package)
            payload = Path(package).read_bytes()
            if sha(payload) != item['sha256']: raise ValueError('Pacote não corresponde ao catálogo.')
            from manager import validate_vpk
            validate_vpk(package,'map' if slot=='map' else 'skin',hero=slot.removeprefix('skin:') if slot.startswith('skin:') else None,game_path=self.game)
            if slot.startswith('skin:'):
                from vpk_lab import index
                incoming = index(package)[1]
                for other in record['slots']:
                    if other == slot or not other.startswith('skin:'): continue
                    existing = index(self.target(other,record))[1]
                    clashes = [p for p in incoming.keys() & existing.keys() if (incoming[p][0],incoming[p][3],incoming[p][4]) != (existing[p][0],existing[p][3],existing[p][4])]
                    if clashes: raise ValueError('Este pacote conflita com '+other+'. Desative esse herói antes de aplicar.')
        else:
            if slot not in record['slots']: return
            payload = self.restore_bytes(record['originals'][slot])
        target = self.target(slot,record)
        original = target.read_bytes() if target.exists() else None
        if slot not in record['slots'] and slot in record['originals']:
            if (sha(original) if original is not None else None) != record['originals'][slot]:
                raise ValueError('Arquivo do slot desativado mudou fora do aplicativo; nenhuma alteração aplicada.')
        if slot not in record['originals']:
            if slot.startswith('skin:') and original is not None: raise ValueError('Slot do herói já ocupado por outro arquivo.')
            record['originals'][slot] = self.backup(original)
        before_hash = self.backup(original)
        if item is None: record['slots'].pop(slot)
        else: record['slots'][slot] = {'id':item['id'], 'name':item['name'], 'sha256':item['sha256']}
        boot_now = self.boot.read_bytes()
        boot_next = base64.b64decode(record['boot_after'] if record['slots'] else record['boot_before'])
        changes = [{'slot':slot,'before':before_hash,'after':sha(payload) if payload is not None else None}, {'slot':'boot','before':self.backup(boot_now),'after':sha(boot_next)}]
        pending = copy.deepcopy(record)
        pending['pending'] = {'changes':changes,'stable':stable}
        closed()
        self.save(pending)
        try:
            self.write(target,payload,before_hash)
            if boot_now != boot_next: put(self.boot,boot_next,sha(boot_now))
            if self.protected() != protected_now: raise ValueError('Arquivos protegidos mudaram externamente durante a troca.')
            if record['protected']!=protected_now:
                record.setdefault('game_updates',[]).append({'previous':record['protected'],'current':protected_now})
                record['protected']=protected_now
            if not record['slots']:
                record['boot_after'] = record['boot_before']
            self.save(record)
            if record.pop('legacy_migration',False):
                # Archive, retaining the original rollback data.
                if self.legacy.exists():
                    put(self.library/('migrated-'+uuid.uuid4().hex+'.json'),self.legacy.read_bytes(),None)
                    self.legacy.unlink()
                self.save(record)
            if not record['slots']:
                put(self.library/('session-restored-'+uuid.uuid4().hex+'.json'),self.journal.read_bytes(),None)
                self.journal.unlink()
        except Exception:
            if self.read().get('pending'): self.recover()
            raise
