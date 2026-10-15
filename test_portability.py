"""Release checks using synthetic files only: no Dota install, mods or network needed."""
import copy
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import uuid
from zipfile import ZipFile

from app_lock import AppLock
from manager import Library
from mod_session import Session
from packages import CATALOG
from skin_builder import SkinBuilder
from terrain_updater import TerrainUpdater
from tide_trial import PROTECTED, sha
from vpk_lab import write_single
from cosmetic_schema import ASSEMBLY_REVISION, recipe_signature


class PortabilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.game = self.root/'steam-library/game'
        for name in (*PROTECTED, 'dota_russian/gameinfo.gi'):
            path = self.game/name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'official original')
        boot = self.game/'dota/cfg/boot.vcfg'
        boot.parent.mkdir(parents=True)
        boot.write_bytes(b'"boot"\r\n{\r\n"AudioLanguage" "english"\r\n"UILanguage" "brazilian"\r\n}\r\n')
        maps = self.game/'dota/maps'
        maps.mkdir()
        write_single(maps/'dota.vpk', {'maps/dota.vmap_c': b'root', 'maps/dota/world.vwrld_c': b'world', 'maps/dota/nav.gnv': b'nav'})
        for item in CATALOG['terrains']:
            name = item['native_map']
            write_single(maps/(name+'.vpk'), {f'maps/{name}.vmap_c': b'root', f'maps/{name}/world.vwrld_c': name.encode()})
        write_single(self.game/'dota/pak01_dir.vpk', {'materials/test.vmat_c': b'official material'})
        with patch('manager.find_dota_installations', return_value=[]):
            self.library = Library(self.root/'user-local-data')
        self.library.set_game_path(self.game)
        self.session = Session(self.game, self.library.root)

    def snapshot(self):
        return {p.relative_to(self.game).as_posix(): p.read_bytes() for p in self.game.rglob('*') if p.is_file()}

    def skin(self):
        path = self.root/'skin.vpk'
        write_single(path, {'models/heroes/tidehunter/tidehunter.vmdl_c': b'synthetic cosmetic'})
        key = sha(path.read_bytes())
        destination = self.library.root/'skins'/(key+'.vpk')
        destination.parent.mkdir(exist_ok=True)
        destination.write_bytes(path.read_bytes())
        return self.library.register_generated_skin({'hero': 'tidehunter', 'id': 'megalodon', 'sha256': key,
            'local_file': 'skins/'+key+'.vpk', 'game_path': str(self.game.resolve()), 'resources': 1,
            'assembly_revision': ASSEMBLY_REVISION,
            'recipe_sha256': recipe_signature(json.loads((Path(__file__).parent/'assets/skin-recipes.json').read_text('utf-8'))['styles']['megalodon']),
            'official_sources': {'dota/pak01_dir.vpk': sha((self.game/'dota/pak01_dir.vpk').read_bytes())}})

    @patch('mod_session.closed')
    def test_generated_skin_only_changes_declared_files_and_restores_exact_bytes(self, _):
        before = self.snapshot()
        item = self.skin()
        self.session.change('skin:tidehunter', item, item['package_path'])
        after = self.snapshot()
        changed = {p for p in before.keys() | after.keys() if before.get(p) != after.get(p)}
        self.assertEqual(changed, {'dota/cfg/boot.vcfg', 'dota_russian/pak98_dir.vpk'})
        self.session.change('skin:tidehunter')
        self.assertEqual(self.snapshot(), before)

    def test_clean_pc_builds_terrains_even_when_hashes_match_shipped_catalog(self):
        updater = TerrainUpdater(self.game, self.library.root)
        templates = copy.deepcopy(CATALOG['terrains'])
        for item in templates:
            item['original_game_sha256'] = sha(updater.sources()[item['native_map']].read_bytes())
            item['original_default_sha256'] = sha(updater.sources()['dota'].read_bytes())
        with patch.dict(CATALOG, {'terrains': templates}):
            self.assertEqual(len(updater.update()['rebuilt']), len(templates))
            self.assertTrue(all(updater.package(p, self.root/'empty-assets').is_file() for p in updater.catalog()))

    @patch('mod_session.closed')
    def test_existing_terrain_and_boot_restore_after_skin_and_terrain(self, _):
        target = self.game/'dota_russian/maps/dota.vpk'
        target.parent.mkdir()
        target.write_bytes(b'pre-existing map mod owned by user')
        before = self.snapshot()
        updater = TerrainUpdater(self.game, self.library.root)
        updater.update()
        terrain = updater.catalog()[0]
        self.session.change('map', terrain, updater.package(terrain, self.root))
        item = self.skin()
        self.session.change('skin:tidehunter', item, item['package_path'])
        self.session.change('map')
        self.session.change('skin:tidehunter')
        self.assertEqual(self.snapshot(), before)

    def test_game_update_invalidates_generated_skin_cache(self):
        self.skin()
        self.assertIsNotNone(self.library.generated_skin('tidehunter', 'megalodon'))
        (self.game/'dota/pak01_dir.vpk').write_bytes(b'official game update')
        self.assertIsNone(self.library.generated_skin('tidehunter', 'megalodon'))

    def test_older_assembly_and_changed_recipe_are_not_reused(self):
        self.skin()
        record=self.library.state['generated_skins']['tidehunter:megalodon']
        record.pop('assembly_revision')
        self.assertIsNone(self.library.generated_skin('tidehunter','megalodon'))
        record['assembly_revision']=ASSEMBLY_REVISION
        record['recipe_sha256']='0'*64
        self.assertIsNone(self.library.generated_skin('tidehunter','megalodon'))

    @patch('mod_session.closed')
    def test_external_boot_change_is_preserved(self, _):
        item = self.skin()
        self.session.change('skin:tidehunter', item, item['package_path'])
        external = self.session.boot.read_bytes()+b'// changed outside Atelier'
        self.session.boot.write_bytes(external)
        with self.assertRaises(ValueError):
            self.session.change('skin:tidehunter')
        self.assertEqual(self.session.boot.read_bytes(), external)

    @patch('mod_session.closed')
    def test_write_failure_rolls_back(self, _):
        import mod_session
        before = self.snapshot()
        item = self.skin()
        real_put = mod_session.put
        failed = False
        def fail_boot_once(path, payload, expected):
            nonlocal failed
            if Path(path) == self.session.boot and not failed:
                failed = True
                raise OSError('simulated failure writing audio setting')
            return real_put(path, payload, expected)
        with patch('mod_session.put', side_effect=fail_boot_once):
            with self.assertRaises(OSError):
                self.session.change('skin:tidehunter', item, item['package_path'])
        self.assertEqual(self.snapshot(), before)
        self.assertIsNone(self.session.read())

    @patch('mod_session.closed')
    def test_restart_recovers_interrupted_install(self, _):
        item = self.skin()
        self.session.change('skin:tidehunter', item, item['package_path'])
        stable = self.session.read()
        target = self.session.target('skin:tidehunter', stable)
        previous = self.session.backup(target.read_bytes())
        pending = copy.deepcopy(stable)
        pending['pending'] = {'stable': stable, 'changes': [{'slot': 'skin:tidehunter', 'before': previous, 'after': sha(b'interrupted replacement')}]}
        self.session.save(pending)
        target.write_bytes(b'interrupted replacement')
        Session(self.game, self.library.root).recover()
        self.assertEqual(self.session.read(), stable)
        self.assertEqual(sha(target.read_bytes()), item['sha256'])

    def test_slots_do_not_depend_on_catalog_sort_order(self):
        record = {'language': 'russian'}
        expected = self.session.target('skin:wisp', record)
        with patch.dict(CATALOG, {'heroes': list(reversed(CATALOG['heroes']))}):
            self.assertEqual(self.session.target('skin:wisp', record), expected)

    def builder(self):
        manifest = self.root/'recipes.json'
        manifest.write_text(json.dumps({'schema_version': 1, 'source_commit': 'a'*40,
            'heroes': {'razor': {'id': 'razor', 'resources': ['models/heroes/razor/razor.vmdl_c'], 'aliases': {}}}}), 'utf-8')
        return SkinBuilder(self.game, self.library.root, manifest)

    def test_download_rejects_data_that_does_not_match_pin(self):
        builder = self.builder()
        expected = b'expected zip bytes'
        recipe = {'source_zip': 'assets/files/heroes/test.zip', 'source_size': len(expected),
                  'source_git_blob_sha1': builder._git_blob_sha1(expected), 'source_sha256': sha(expected)}
        with patch('skin_builder.urlopen', return_value=io.BytesIO(b'x'*len(expected))):
            with self.assertRaises(ValueError): builder._download_zip(recipe, lambda _: None)
        self.assertFalse(list(builder.cache.glob('*.zip')))

    def test_zip_path_traversal_is_rejected(self):
        builder = self.builder()
        archive = self.root/'bad.zip'
        with ZipFile(archive, 'w') as output: output.writestr('../outside.vpk', b'invalid')
        with self.assertRaises(ValueError): builder._extract_vpk(archive, self.root)
        self.assertFalse((self.root.parent/'outside.vpk').exists())

    def test_game_update_during_skin_build_does_not_publish_package(self):
        builder = self.builder()
        source = self.root/'source.vpk'
        write_single(source, {'models/heroes/razor/razor.vmdl_c': b'synthetic cosmetic'})
        archive = self.root/'source.zip'
        with ZipFile(archive, 'w') as output: output.write(source, 'hero.vpk')
        def simulate_update(_entries): (self.game/'dota/pak01_dir.vpk').write_bytes(b'new official bytes')
        with patch.object(builder, '_download_zip', return_value=archive), patch.object(builder, '_apply_wearables', return_value={}), patch.object(builder, '_validate_references', side_effect=simulate_update):
            with self.assertRaisesRegex(ValueError, 'atualizou durante'):
                builder.prepare('razor', 'razor')
        self.assertFalse(list(builder.skin_dir.glob('*.vpk')))

    @unittest.skipUnless(os.name == 'nt', 'Windows named mutex')
    def test_second_instance_is_blocked_and_lock_releases(self):
        name = 'Local\\DotaAtelier.Test.'+uuid.uuid4().hex
        first, second = AppLock(name), AppLock(name)
        self.addCleanup(first.release)
        self.addCleanup(second.release)
        self.assertTrue(first.acquire())
        self.assertFalse(second.acquire())
        first.release()
        self.assertTrue(second.acquire())


if __name__ == '__main__': unittest.main()
