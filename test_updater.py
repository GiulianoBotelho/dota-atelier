import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from packages import CATALOG
from terrain_updater import TerrainUpdater
from mod_session import Session
from tide_trial import PROTECTED
from vpk_lab import write_single,read_single

class UpdaterTests(unittest.TestCase):
    def fixture(self,root):
        game=root/'game';maps=game/'dota/maps';maps.mkdir(parents=True)
        for p in (*PROTECTED,'dota_russian/gameinfo.gi'):
            file=game/p;file.parent.mkdir(parents=True,exist_ok=True);file.write_bytes(b'original game file')
        boot=game/'dota/cfg/boot.vcfg';boot.parent.mkdir(parents=True);boot.write_bytes(b'"AudioLanguage" "english"\n"UILanguage" "brazilian"')
        default={'maps/dota.vmap_c':b'current root','maps/dota/world.vwrld_c':b'current world','maps/dota/nav.gnv':b'current nav'}
        write_single(maps/'dota.vpk',default)
        for item in CATALOG['terrains']:
            name=item['native_map'];write_single(maps/(name+'.vpk'),{f'maps/{name}.vmap_c':b'terrain root',f'maps/{name}/world.vwrld_c':name.encode()})
        updater=TerrainUpdater(game,root/'library');session=Session(game,root/'library')
        return updater,session,default

    def test_rebuild_latest_resources_and_report_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            updater,session,default=self.fixture(Path(tmp))
            result=updater.update()
            self.assertEqual(len(result['rebuilt']),12)
            item=updater.catalog()[0];data=read_single(updater.package(item,Path('.')))
            self.assertEqual(data['maps/dota/nav.gnv'],default['maps/dota/nav.gnv'])
            self.assertEqual(data['maps/dota/world.vwrld_c'],item['native_map'].encode())
            self.assertEqual(len(updater.update()['rebuilt']),0)
            default['maps/dota/nav.gnv']=b'nav after patch';default['maps/dota/entities/new.vents_c']=b'new entities'
            write_single(updater.sources()['dota'],default)
            result=updater.update()
            self.assertEqual(len(result['rebuilt']),12)
            self.assertIn('maps/dota/nav.gnv',result['source_changes']['dota']['changed'])
            self.assertIn('maps/dota/entities/new.vents_c',result['source_changes']['dota']['added'])
            new=updater.catalog()[0]
            self.assertNotEqual(new['sha256'],item['sha256'])
            self.assertEqual(read_single(updater.package(new,Path('.')))['maps/dota/nav.gnv'],b'nav after patch')

    @patch('mod_session.closed')
    def test_reapply_active_terrain_after_engine_patch(self,_):
        with tempfile.TemporaryDirectory() as tmp:
            updater,session,default=self.fixture(Path(tmp));before=session.boot.read_bytes()
            updater.update();item=updater.catalog()[0]
            session.change('map',item,updater.package(item,Path('.')))
            protected=(session.game/PROTECTED[-1]);protected.write_bytes(b'new official engine after Steam patch')
            default['maps/dota/nav.gnv']=b'new nav';write_single(updater.sources()['dota'],default)
            result=updater.update(session)
            self.assertTrue(result['active_terrain_reapplied'])
            self.assertEqual(session.state()['slots']['map']['id'],item['id'])
            self.assertEqual(session.state()['slots']['map']['sha256'],updater.catalog()[0]['sha256'])
            session.change('map')
            self.assertEqual(session.boot.read_bytes(),before)
            self.assertEqual(protected.read_bytes(),b'new official engine after Steam patch')

    def test_source_changes_during_generation_prevent_publish(self):
        with tempfile.TemporaryDirectory() as tmp:
            updater,_,_=self.fixture(Path(tmp))
            with patch.object(updater,'fingerprint',side_effect=[('before',),('after',)]):
                with self.assertRaises(ValueError):updater.update()
            self.assertFalse(updater.manifest.exists())

    @patch('mod_session.closed')
    def test_generated_catalog_cannot_authorize_arbitrary_payload(self,_):
        with tempfile.TemporaryDirectory() as tmp:
            updater,session,_=self.fixture(Path(tmp));updater.update();item=updater.catalog()[0]
            package=updater.package(item,Path('.'));write_single(package,{'maps/dota.vmap_c':b'tampered'})
            with self.assertRaises(ValueError):session.change('map',item,package)
            self.assertFalse(session.journal.exists())

    def test_unknown_map_format_preserves_catalog(self):
        with tempfile.TemporaryDirectory() as tmp:
            updater,_,_=self.fixture(Path(tmp));updater.update();before=updater.manifest.read_bytes()
            write_single(updater.sources()['dota'],{'maps/dota.vmap_c':b'new unsupported format'})
            with self.assertRaises(ValueError):updater.update()
            self.assertEqual(updater.manifest.read_bytes(),before)

    @patch('mod_session.closed',side_effect=ValueError('game running'))
    def test_running_game_prevents_reapplication(self,_):
        with tempfile.TemporaryDirectory() as tmp:
            updater,session,_=self.fixture(Path(tmp));updater.update();item=updater.catalog()[0]
            with self.assertRaises(ValueError):session.change('map',item,updater.package(item,Path('.')))
            self.assertFalse(session.journal.exists())

if __name__=='__main__':unittest.main()
