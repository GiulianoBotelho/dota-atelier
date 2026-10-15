"""Reversible additive cosmetic experiment. Only apply after the displayed plan is accepted.

Writes are restricted to one extra VPK and the ordinary AudioLanguage setting.
Never writes engine configuration, signatures, executables or Steam configuration.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import uuid

LEGACY_SHA = '79966dd334c039078feb9ea6e77a613a0f3ba0fcbfd65b5eadd79b52e497a3b7'
APPROVED_SHA = '2b8899c7e6036c613d59b6e55bca581b4701c82693e36284b0c509ad677e6248'
KNOWN_PACKAGES = {LEGACY_SHA, APPROVED_SHA}
PROTECTED = ('dota/gameinfo.gi', 'dota/gameinfo_branchspecific.gi', 'bin/win64/dota.signatures', 'bin/win64/dota2.exe')
AUDIO = re.compile(rb'("AudioLanguage"\s*")([^"\r\n]+)(")')

def sha(data): return hashlib.sha256(data).hexdigest()

def clean_path(path):
    path = Path(path).absolute()
    for part in (path, *path.parents):
        if part.is_symlink() or (part.exists() and getattr(part.lstat(), 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT):
            raise ValueError('Caminho redirecionado não permitido: '+str(part))
    return path

def closed():
    result = subprocess.run(['tasklist', '/FO', 'CSV', '/NH'], capture_output=True, text=True, creationflags=0x08000000, check=True)
    if '"dota2.exe"' in result.stdout.lower():
        raise ValueError('Feche o Dota antes de aplicar ou desfazer o teste.')

def put(path, data, expected):
    path = clean_path(path)
    before = path.read_bytes() if path.exists() else None
    if (sha(before) if before is not None else None) != expected:
        raise ValueError('Arquivo mudou fora do aplicativo: '+str(path))
    temporary = path.with_name(path.name+'.atelier-'+uuid.uuid4().hex+'.tmp')
    try:
        with temporary.open('xb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if expected is None:
            # Windows rename refuses an existing destination.
            os.rename(temporary, path)
        else:
            if sha(path.read_bytes()) != expected:
                raise ValueError('Arquivo alterado durante a operação.')
            os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)

class Trial:
    def __init__(self, game, library):
        self.game = clean_path(game)
        self.library = clean_path(library)
        self.library.mkdir(parents=True, exist_ok=True)
        self.journal = self.library/'tidehunter-trial.json'
        self.boot = clean_path(self.game/'dota/cfg/boot.vcfg')

    def protected(self):
        return {p:sha(clean_path(self.game/p).read_bytes()) for p in PROTECTED}

    def plan(self, package):
        if self.journal.exists():
            raise ValueError('Já existe um teste registrado. Use Desfazer teste antes de aplicar novamente.')
        package = Path(package)
        payload = package.read_bytes()
        if sha(payload) != APPROVED_SHA:
            raise ValueError('Este botão aceita somente o pacote visual do Tidehunter revisado.')
        original = self.boot.read_bytes()
        matches = list(AUDIO.finditer(original))
        if len(matches) != 1: raise ValueError('Configuração de áudio ausente ou ambígua.')
        audio = matches[0].group(2).decode('ascii')
        if audio not in ('english', 'russian', 'koreana', 'schinese'):
            raise ValueError('Idioma atual requer revisão manual; nenhuma mudança aplicada.')
        language = 'russian' if audio == 'english' else audio
        folder = clean_path(self.game/('dota_'+language))
        if not (folder/'gameinfo.gi').is_file():
            raise ValueError('Pasta de idioma oficial ausente.')
        if audio == 'english' and list(folder.glob('pak01*.vpk')):
            raise ValueError('Pacote de voz russo instalado. Não alteraremos suas vozes automaticamente.')
        # This experiment runs alone: avoid priority conflicts with other packages.
        foreign = [p.name for p in folder.glob('*.vpk') if not p.name.startswith('pak01')]
        if foreign: raise ValueError('Já existem mods na pasta de áudio: '+', '.join(foreign))
        target = clean_path(folder/'pak98_dir.vpk')
        if target.exists() or target.with_suffix('.vpk.off').exists():
            raise ValueError('Slot pak98 já ocupado.')
        patched = AUDIO.sub(lambda m:m.group(1)+language.encode()+m.group(3), original)
        return {'game':str(self.game), 'target':str(target), 'package_sha256':APPROVED_SHA,
                'audio_before':audio, 'audio_after':language,
                'boot_before':base64.b64encode(original).decode(),
                'boot_after':base64.b64encode(patched).decode(),
                'protected_before':self.protected(), 'status':'prepared'}

    def save(self, record):
        data = json.dumps(record, ensure_ascii=False, indent=2).encode('utf-8')
        old = sha(self.journal.read_bytes()) if self.journal.exists() else None
        put(self.journal, data, old)

    def state(self):
        """Read actual files, never infer activation from catalog membership."""
        if not self.journal.exists():
            return 'inactive'
        try:
            record = json.loads(self.journal.read_text('utf-8'))
            if record['game'] != str(self.game) or record['audio_after'] not in ('russian', 'koreana', 'schinese'):
                return 'conflict'
            target = clean_path(self.game/('dota_'+record['audio_after'])/'pak98_dir.vpk')
            if record['package_sha256'] not in KNOWN_PACKAGES or not target.exists(): return 'conflict'
            if sha(target.read_bytes()) != record['package_sha256']: return 'conflict'
            if self.boot.read_bytes() != base64.b64decode(record['boot_after']): return 'conflict'
            return 'active' if record['package_sha256'] == APPROVED_SHA else 'legacy'
        except (OSError, ValueError, KeyError):
            return 'conflict'

    def apply(self, package, reviewed_plan):
        closed()
        fresh = self.plan(package)
        if fresh != reviewed_plan:
            raise ValueError('O plano mudou. Abra a revisão novamente.')
        self.save(fresh)
        try:
            put(Path(fresh['target']), Path(package).read_bytes(), None)
            before = base64.b64decode(fresh['boot_before'])
            after = base64.b64decode(fresh['boot_after'])
            if before != after: put(self.boot, after, sha(before))
            if self.protected() != fresh['protected_before']:
                raise ValueError('Arquivos protegidos mudaram externamente durante o teste.')
            fresh['status'] = 'installed_not_visually_tested'
            self.save(fresh)
        except Exception:
            self.undo()
            raise

    def undo(self):
        closed()
        if not self.journal.exists(): raise ValueError('Nenhum teste para desfazer.')
        record = json.loads(self.journal.read_text('utf-8'))
        if record['game'] != str(self.game): raise ValueError('Registro de outra instalação.')
        expected_folder = self.game/('dota_'+record['audio_after'])
        if record['audio_after'] not in ('russian','koreana','schinese'):
            raise ValueError('Registro de idioma inválido.')
        target = clean_path(expected_folder/'pak98_dir.vpk')
        before = base64.b64decode(record['boot_before'])
        after = base64.b64decode(record['boot_after'])
        current = self.boot.read_bytes()
        if current not in (before, after):
            raise ValueError('O jogo alterou boot.vcfg. Preserve o registro e restaure o idioma manualmente; nenhuma mudança aplicada.')
        if record['package_sha256'] not in KNOWN_PACKAGES:
            raise ValueError('Pacote desconhecido no registro.')
        if target.exists() and sha(target.read_bytes()) != record['package_sha256']:
            raise ValueError('O VPK foi alterado externamente; remoção automática interrompida.')
        if current != before: put(self.boot, before, sha(current))
        if target.exists(): target.unlink()
        record['status'] = 'restored'
        put(self.library/('tidehunter-restored-'+uuid.uuid4().hex+'.json'), json.dumps(record,indent=2).encode(), None)
        self.journal.unlink()
