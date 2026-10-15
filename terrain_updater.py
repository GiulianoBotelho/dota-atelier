"""Rebuild terrain overlays from current official sources; no network or engine patches."""
import copy
import json
from pathlib import Path
import re
import tempfile
from datetime import datetime,timezone
from packages import CATALOG
from tide_trial import clean_path, put, sha
from vpk_lab import read_single, write_single

class TerrainUpdater:
    def __init__(self,game,library):
        self.game,self.root=clean_path(game),clean_path(Path(library)/'terrain-updates')
        self.root.mkdir(parents=True,exist_ok=True)
        self.manifest=self.root/'catalog.json'
        self.report=self.root/'last-update.json'

    def sources(self):
        folder=self.game/'dota/maps'
        return {'dota':clean_path(folder/'dota.vpk'),**{p['native_map']:clean_path(folder/(p['native_map']+'.vpk')) for p in CATALOG['terrains']}}

    def fingerprint(self):
        return tuple((name,p.stat().st_size,p.stat().st_mtime_ns,p.stat().st_ctime_ns) for name,p in self.sources().items())

    def steam_ready(self):
        manifest=self.game.parents[2]/'appmanifest_570.acf'
        if not manifest.exists():return
        text=manifest.read_text('utf-8')
        flag=re.search(r'"StateFlags"\s*"(\d+)"',text)
        if not flag or int(flag.group(1))!=4:
            raise ValueError('Aguardando o Steam concluir a atualização do Dota.')

    def load(self):
        if not self.manifest.exists():return None
        data=json.loads(self.manifest.read_text('utf-8'))
        if data['game']!=str(self.game):raise ValueError('Catálogo de atualização pertence a outro Dota.')
        expected={p['id']:p['native_map'] for p in CATALOG['terrains']}
        if len(data['terrains'])!=len(expected) or {p['id']:p['native_map'] for p in data['terrains']}!=expected:
            raise ValueError('Catálogo de terrenos atualizado é inválido.')
        return data

    def catalog(self):
        data=self.load()
        return data['terrains'] if data else CATALOG['terrains']

    def package(self,item,assets):
        if item.get('generated'):
            key=item['sha256']
            if len(key)!=64 or any(c not in '0123456789abcdef' for c in key):raise ValueError('Hash de terreno inválido.')
            return clean_path(self.root/(key+'.vpk'))
        return Path(assets)/item['file']

    @staticmethod
    def combine(default,native,name):
        if 'maps/dota/world.vwrld_c' not in default or 'maps/dota.vmap_c' not in default:
            raise ValueError('Formato do mapa padrão mudou; atualização automática interrompida.')
        own='maps/'+name
        if not any(p in native for p in ('maps/dota/world.vwrld_c',own+'/world.vwrld_c')):
            raise ValueError('Formato do terreno mudou; atualização automática interrompida.')
        output=dict(default)
        output.update(native)
        for path,payload in native.items():
            if path.startswith(own+'/'):output['maps/dota/'+path.removeprefix(own+'/')]=payload
            elif path==own+'.vmap_c':output['maps/dota.vmap_c']=payload
        return output

    def validate_generated(self,item,package):
        data=self.load()
        if not data or not any(item==p for p in data['terrains']):raise ValueError('Terreno gerado não registrado.')
        template=next(p for p in CATALOG['terrains'] if p['id']==item['id'])
        sources=self.sources()
        default=read_single(sources['dota'])
        native=read_single(sources[template['native_map']])
        expected=self.combine(default,native,template['native_map'])
        if read_single(package)!=expected:raise ValueError('Pacote gerado difere dos recursos oficiais atuais.')

    def update(self,session=None):
        self.steam_ready()
        fingerprint=self.fingerprint()
        previous=self.load()
        source_data={name:read_single(path) for name,path in self.sources().items()}
        hashes={name:sha(path.read_bytes()) for name,path in self.sources().items()}
        snapshots={name:{p:sha(b) for p,b in entries.items()} for name,entries in source_data.items()}
        changes={}
        old_snapshots=previous.get('snapshots',{}) if previous else {}
        for name,current in snapshots.items():
            old=old_snapshots.get(name)
            if old is not None:
                changed=[p for p in current.keys()&old.keys() if current[p]!=old[p]]
                added=sorted(current.keys()-old.keys());removed=sorted(old.keys()-current.keys())
                if changed or added or removed:changes[name]={'changed':sorted(changed),'added':added,'removed':removed}
        terrains=[]
        rebuilt=[]
        from manager import validate_vpk
        for template in CATALOG['terrains']:
            item=copy.deepcopy(template)
            native=template['native_map']
            old=next((p for p in previous['terrains'] if p['id']==item['id']),None) if previous else template
            current=(hashes[native],hashes['dota'])
            if old and current==(old['original_game_sha256'],old['original_default_sha256']):
                if old.get('generated'):
                    cached=self.package(old,Path('.'))
                    if cached.is_file() and sha(cached.read_bytes())==old['sha256']:
                        terrains.append(old);continue
            resources=self.combine(source_data['dota'],source_data[native],native)
            with tempfile.TemporaryDirectory(dir=self.root,prefix='build-') as tmp:
                temporary=Path(tmp)/'dota.vpk';write_single(temporary,resources);validate_vpk(temporary)
                payload=temporary.read_bytes();key=sha(payload);target=self.root/(key+'.vpk')
                if target.exists():
                    if sha(target.read_bytes())!=key:raise ValueError('Pacote atualizado corrompido.')
                else:put(target,payload,None)
            item.update({'sha256':key,'original_game_sha256':hashes[native],'original_default_sha256':hashes['dota'],'generated':True,'resources':len(resources),'source':'Reconstruído com os arquivos oficiais atuais do Dota; bytes compilados preservados.'})
            terrains.append(item);rebuilt.append(item['id'])
        self.steam_ready()
        if fingerprint!=self.fingerprint():raise ValueError('O Steam alterou os mapas durante a geração. Aguarde e tente novamente.')
        data={'game':str(self.game),'terrains':terrains,'sources':hashes,'snapshots':snapshots}
        put(self.manifest,json.dumps(data,ensure_ascii=False,indent=2).encode(),sha(self.manifest.read_bytes()) if self.manifest.exists() else None)
        report={'checked_at_utc':datetime.now(timezone.utc).isoformat(),'previous_source_hashes':previous.get('sources') if previous else None,'current_source_hashes':hashes,'rebuilt':rebuilt,'source_changes':changes,'baseline_created':previous is None,'active_terrain_reapplied':False}
        if session is not None:
            state=session.state()
            active=state['slots'].get('map')
            if state['conflict']:raise ValueError(state['conflict'])
            if active:
                item=next(p for p in terrains if p['id']==active['id'])
                if active['sha256']!=item['sha256']:
                    session.change('map',item,self.package(item,Path('.')))
                    report['active_terrain_reapplied']=True
        put(self.report,json.dumps(report,ensure_ascii=False,indent=2).encode(),sha(self.report.read_bytes()) if self.report.exists() else None)
        if rebuilt or changes or previous is None:
            history=self.root/'history';history.mkdir(exist_ok=True)
            key=sha(json.dumps(hashes,sort_keys=True).encode())
            destination=history/(key+'.json')
            if not destination.exists():put(destination,json.dumps(report,ensure_ascii=False,indent=2).encode(),None)
        return report
