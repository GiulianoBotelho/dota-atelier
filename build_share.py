"""Create shareable source and portable archives without game/mod VPK files."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile
import hashlib

ROOT=Path(__file__).resolve().parent
DIST=ROOT/'dist'
BUILD=ROOT/'build'
RUNTIME=('manager.py','desktop_ui.py','packages.py','steam_discovery.py','mod_session.py',
         'terrain_updater.py','tide_trial.py','vpk_lab.py','skin_builder.py','app_lock.py','version.py','DotaAtelier.spec',
         'README.md','THIRD_PARTY_LICENSES.txt','Dota2PornFx-LICENSE.txt',
         'requirements-build.txt','build_share.py','LICENSE','COMPATIBILITY.md','test_portability.py','test_updater.py',
         '.gitignore','CHANGELOG.md','.github/workflows/verify.yml')
IMAGE_SUFFIXES={'.png','.webp','.jpg','.jpeg'}

def safe_zip_tree(zip_path,base,folder,prefix=''):
    for path in sorted(folder.rglob('*')):
        if path.is_file():
            relative=Path(prefix)/path.relative_to(folder)
            zip_path.write(path,relative.as_posix())

def main():
    DIST.mkdir(exist_ok=True)
    BUILD.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='dota-atelier-share-',dir=BUILD) as temporary:
        temp=Path(temporary)
        source=temp/'source'
        assets=source/'assets'
        assets.mkdir(parents=True)
        for filename in RUNTIME:
            path=ROOT/filename
            if not path.is_file():raise FileNotFoundError('Arquivo de release ausente: '+filename)
            target=source/filename
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(path,target)
        shutil.copytree(ROOT/'licenses',source/'licenses')
        for path in (ROOT/'assets').rglob('*'):
            if not path.is_file():continue
            if path.suffix.casefold() not in IMAGE_SUFFIXES and path.name not in {'catalog.json','skin-recipes.json'}:continue
            if path.name.casefold()=='dota-logo.png':continue
            relative=path.relative_to(ROOT/'assets')
            target=assets/relative
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(path,target)

        dist=temp/'dist'
        work=temp/'work'
        spec=temp/'generated-spec'
        spec.mkdir()
        subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--clean','--windowed','--onedir',
                        '--name','DotaAtelier','--add-data',f'{assets};assets',
                        '--distpath',str(dist),'--workpath',str(work),
                        '--specpath',str(spec),str(source/'manager.py')],
                       cwd=source,check=True)
        shutil.copy2(source/'README.md',dist/'DotaAtelier'/'README.md')
        shutil.copy2(source/'COMPATIBILITY.md',dist/'DotaAtelier'/'COMPATIBILITY.md')
        shutil.copy2(source/'LICENSE',dist/'DotaAtelier'/'LICENSE')
        shutil.copy2(source/'THIRD_PARTY_LICENSES.txt',dist/'DotaAtelier'/'THIRD_PARTY_LICENSES.txt')
        shutil.copy2(source/'Dota2PornFx-LICENSE.txt',dist/'DotaAtelier'/'Dota2PornFx-LICENSE.txt')
        shutil.copytree(source/'licenses',dist/'DotaAtelier'/'licenses')

        portable=DIST/'DotaAtelier-Compartilhar.zip'
        with zipfile.ZipFile(portable,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
            safe_zip_tree(archive,dist,dist/'DotaAtelier','Dota Atelier')

        source_zip=DIST/'DotaAtelier-Fonte.zip'
        with zipfile.ZipFile(source_zip,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
            safe_zip_tree(archive,source,source,'Dota Atelier')
        for archive_path in (portable,source_zip):
            with zipfile.ZipFile(archive_path) as archive:
                forbidden = [n for n in archive.namelist() if n.lower().endswith('.vpk')
                             or Path(n).name in {'state.json', 'cosmetic-session.json'}]
                if forbidden: raise ValueError('Dados locais proibidos no release: '+', '.join(forbidden))
                if archive_path == source_zip:
                    for filename in RUNTIME:
                        if archive.read('Dota Atelier/'+filename) != (ROOT/filename).read_bytes():
                            raise ValueError('Fonte alterado durante o build: '+filename)
            with archive_path.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
            archive_path.with_suffix(archive_path.suffix+'.sha256').write_text(f'{digest}  {archive_path.name}\n',encoding='ascii')
        print(f'Portable: {portable} ({portable.stat().st_size:,} bytes)')
        print(f'Fonte:    {source_zip} ({source_zip.stat().st_size:,} bytes)')
        print('VPKs incluidos: 0')

if __name__=='__main__':main()
