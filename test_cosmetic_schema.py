import copy
from pathlib import Path
import tempfile
import unittest

from cosmetic_schema import read_schema, wearable_aliases, INVISIBLE_MODEL, recipe_signature
from vpk_lab import write_single, read_single, index


class CosmeticSchemaTests(unittest.TestCase):
    unit = 'npc_dota_hero_spectre'
    default = 'models/heroes/spectre/spectre_hat.vmdl_c'

    def schema(self):
        return {'prefabs': {}, 'items': {
            '1': {'prefab': 'default_item', 'item_slot': 'head',
                  'model_player': self.default[:-2], 'used_by_heroes': {self.unit: '1'}},
            '2': {'item_slot': 'head', 'model_player': 'models/items/spectre/owned_hat.vmdl',
                  'used_by_heroes': {self.unit: '1'},
                  'visuals': {'styles': {'1': {'model_player': 'models/items/spectre/owned_hat_style2.vmdl'}}}},
        }}

    def test_owned_item_and_style_use_same_arcana_slot(self):
        schema = self.schema(); before = copy.deepcopy(schema)
        aliases, report = wearable_aliases(schema, 'spectre', {self.default})
        self.assertEqual(set(aliases.values()), {self.default})
        self.assertEqual(len(aliases), 2)
        self.assertNotIn(self.default, aliases)
        self.assertEqual(schema, before)
        self.assertFalse(report['ambiguous_models'])

    def test_empty_default_slot_uses_invisible_geometry(self):
        schema = self.schema(); schema['items']['1'].pop('model_player')
        aliases, _ = wearable_aliases(schema, 'spectre', {INVISIBLE_MODEL})
        self.assertEqual(set(aliases.values()), {INVISIBLE_MODEL})

    def test_shared_item_is_not_changed_for_other_heroes(self):
        schema = self.schema(); schema['items']['2']['used_by_heroes']['npc_dota_hero_lina'] = '1'
        aliases, report = wearable_aliases(schema, 'spectre', {self.default})
        self.assertFalse(aliases)
        self.assertEqual(report['shared_items_skipped'], ['2'])

    def test_generic_invisible_model_is_never_replaced_globally(self):
        schema = self.schema(); schema['items']['2']['model_player'] = INVISIBLE_MODEL[:-2]
        aliases, report = wearable_aliases(schema, 'spectre', {self.default})
        self.assertNotIn(INVISIBLE_MODEL, aliases)
        self.assertIn(INVISIBLE_MODEL, report['shared_or_generic_models_skipped'])

    def test_separate_items_sharing_model_across_heroes_are_not_overridden(self):
        schema = self.schema()
        schema['items']['3'] = {'item_slot': 'head', 'used_by_heroes': {'npc_dota_hero_lina': '1'},
                              'model_player': schema['items']['2']['model_player']}
        aliases, report = wearable_aliases(schema, 'spectre', {self.default})
        self.assertNotIn('models/items/spectre/owned_hat.vmdl_c', aliases)

    def test_entity_override_is_limited_to_owner_and_excludes_personas(self):
        schema = self.schema()
        schema['items']['2']['visuals'] = {'asset_modifier': [
            {'type': 'entity_model', 'asset': self.unit, 'modifier': 'models/items/spectre/arcana_body.vmdl'},
            {'type': 'entity_model', 'asset': 'npc_dota_lone_druid_bear', 'modifier': 'models/heroes/bear.vmdl'},
            {'type': 'entity_model', 'asset': self.unit, 'modifier': 'models/heroes/spectre_persona/base.vmdl'},
        ]}
        body = 'models/heroes/spectre/spectre.vmdl_c'
        aliases, _ = wearable_aliases(schema, 'spectre', {self.default}, body)
        self.assertEqual(aliases['models/items/spectre/arcana_body.vmdl_c'], body)
        self.assertNotIn('models/heroes/bear.vmdl_c', aliases)
        self.assertNotIn('models/heroes/spectre_persona/base.vmdl_c', aliases)

    def test_ambiguous_models_are_reported_instead_of_guessed(self):
        schema = self.schema()
        schema['items']['3'] = {**schema['items']['1'], 'item_slot': 'weapon', 'model_player': 'models/heroes/spectre/weapon.vmdl'}
        schema['items']['4'] = {**schema['items']['2'], 'item_slot': 'weapon'}
        aliases, report = wearable_aliases(schema, 'spectre', {self.default, 'models/heroes/spectre/weapon.vmdl_c'})
        self.assertFalse(aliases)
        self.assertEqual(len(report['ambiguous_models']), 2)

    def test_reader_preserves_duplicate_visual_modifiers_and_prefabs(self):
        text = '''"items_game" { "ignored" { "x" "y" } "prefabs" { "hat" { "item_slot" "head" } }
        "items" { "1" { "prefab" "hat" "used_by_heroes" { "npc_dota_hero_spectre" "1" }
        "visuals" { "asset_modifier" { "type" "particle" } "asset_modifier" { "type" "entity_model" } } } } }'''
        schema = read_schema(text)
        self.assertEqual(len(schema['items']['1']['visuals']['asset_modifier']), 2)
        from cosmetic_schema import resolve_item
        self.assertEqual(resolve_item(schema['items']['1'], schema['prefabs'])['item_slot'], 'head')

    def test_persona_slots_are_reported_and_not_mixed_with_regular_slots(self):
        schema = self.schema()
        schema['items']['1']['item_slot'] = 'head_persona_1'
        schema['items']['2']['item_slot'] = 'head_persona_1'
        aliases, report = wearable_aliases(schema, 'spectre', {self.default})
        self.assertFalse(aliases)
        self.assertEqual(report['unsupported_persona_slots'], ['head_persona_1'])

    def test_equal_model_payloads_share_bytes_with_independent_names(self):
        entries = {'models/a.vmdl_c': b'synthetic payload'*100, 'models/b.vmdl_c': b'synthetic payload'*100}
        with tempfile.TemporaryDirectory() as folder:
            normal, compact = Path(folder)/'normal.vpk', Path(folder)/'compact.vpk'
            write_single(normal, entries)
            write_single(compact, entries, deduplicate=True)
            self.assertEqual(read_single(compact), entries)
            self.assertLess(compact.stat().st_size, normal.stat().st_size)
            records = list(index(compact)[1].values())
            self.assertEqual(records[0][2], records[1][2])

    def test_recipe_change_invalidates_signature(self):
        self.assertNotEqual(recipe_signature({'id': 'a'}), recipe_signature({'id': 'b'}))

    def test_wearable_model_modifier_is_mapped_to_slot(self):
        from cosmetic_schema import item_model_owners
        schema = self.schema()
        schema['items']['2']['visuals'] = {'asset_modifier': {
            'type': 'model', 'asset': schema['items']['2']['model_player'],
            'modifier': 'models/items/spectre/replacement_hat.vmdl'}}
        aliases, _ = wearable_aliases(schema, 'spectre', {self.default})
        self.assertEqual(aliases['models/items/spectre/replacement_hat.vmdl_c'], self.default)
        self.assertEqual(item_model_owners(schema)['models/items/spectre/replacement_hat.vmdl_c'], {self.unit})

    def test_model_modifier_cannot_replace_another_hero(self):
        schema = self.schema()
        schema['items']['2']['visuals'] = {'asset_modifier': {
            'type': 'model', 'asset': 'models/items/lina/hat.vmdl',
            'modifier': 'models/items/spectre/replacement_hat.vmdl'}}
        aliases, _ = wearable_aliases(schema, 'spectre', {self.default})
        self.assertNotIn('models/items/spectre/replacement_hat.vmdl_c', aliases)

    def test_cross_slot_modifier_uses_replaced_asset_slot(self):
        schema = self.schema()
        belt = 'models/heroes/spectre/belt.vmdl_c'
        schema['items']['3'] = {'prefab': 'default_item', 'item_slot': 'belt',
            'model_player': belt[:-2], 'used_by_heroes': {self.unit: '1'}}
        schema['items']['4'] = {'item_slot': 'belt', 'used_by_heroes': {self.unit: '1'},
            'model_player': 'models/items/spectre/belt.vmdl', 'visuals': {'asset_modifier': {
                'type': 'model', 'asset': schema['items']['2']['model_player'],
                'modifier': 'models/items/spectre/replacement_hat.vmdl'}}}
        aliases, _ = wearable_aliases(schema, 'spectre', {self.default, belt})
        self.assertEqual(aliases['models/items/spectre/replacement_hat.vmdl_c'], self.default)

    def test_animation_include_is_preserved_instead_of_becoming_parent(self):
        from skin_builder import SkinBuilder
        from unittest.mock import patch
        from cosmetic_schema import item_model_owners
        schema = self.schema()
        body = 'models/heroes/spectre/spectre.vmdl_c'
        include = 'models/items/spectre/owned_hat.vmdl_c'
        builder = SkinBuilder.__new__(SkinBuilder)
        builder.game = Path('synthetic-game')
        builder._official_entry = lambda path: b'schema' if path.endswith('items_game.txt') else b'official'
        builder._official_context = lambda: []
        entries = {body: b'parent', self.default: b'canonical', include: b'original include'}
        with patch.object(SkinBuilder, '_schema_cache', (str(builder.game)+'unused', schema, {})), \
             patch('skin_builder.read_schema', return_value=schema), \
             patch('skin_builder.references', side_effect=lambda data: [include[:-2]] if data==b'parent' else []):
            report = builder._apply_wearables(entries, 'spectre')
        self.assertEqual(entries[include], b'original include')
        self.assertEqual(report['preserved_model_dependencies'][include], [body])

    def test_native_models_do_not_inherit_old_community_dependencies(self):
        from skin_builder import SkinBuilder
        builder = SkinBuilder.__new__(SkinBuilder)
        builder._official_entry = lambda path: b'native animation and geometry'
        target = 'models/heroes/wraith_king/wraith_king.vmdl_c'
        source = 'models/items/wraith_king/arcana/wraith_king_arcana.vmdl_c'
        entries = {target: b'old', 'particles/old.vpcf_c': b'old fx',
                   'materials/old.vmat_c': b'old material', 'panorama/images/icon.vtex_c': b'icon'}
        result = builder._local_models({'local_models': {target: source}}, entries)
        self.assertEqual(result, {target: b'native animation and geometry', 'panorama/images/icon.vtex_c': b'icon'})

    def test_model_cycle_is_rejected_even_through_official_include(self):
        from skin_builder import SkinBuilder
        from unittest.mock import patch
        builder = SkinBuilder.__new__(SkinBuilder)
        builder._official_entry = lambda path: b'official include'
        entries = {'models/parent.vmdl_c': b'parent'}
        refs = {b'parent': ['models/include.vmdl'], b'official include': ['models/parent.vmdl']}
        with patch('skin_builder.references', side_effect=lambda data: refs[data]):
            with self.assertRaisesRegex(ValueError, 'circular'):
                builder._validate_model_includes(entries)

    def test_shared_animation_include_is_not_a_cycle(self):
        from skin_builder import SkinBuilder
        from unittest.mock import patch
        builder = SkinBuilder.__new__(SkinBuilder)
        builder._official_entry = lambda path: b'official include'
        entries = {'models/a.vmdl_c': b'parent', 'models/b.vmdl_c': b'parent'}
        with patch('skin_builder.references', side_effect=lambda data:
                   ['models/include.vmdl'] if data==b'parent' else []):
            self.assertEqual(builder._validate_model_includes(entries), 3)

    def test_dynamic_packages_accept_cosmetic_snapshots_and_voice_events_but_not_scripts(self):
        from manager import validate_vpk
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'skin.vpk'
            entries={'particles/hero/effect.vsnap_c':b'snapshot data',
                     'voscripts/hero.vsndevts_c':b'voice event data'}
            write_single(path,entries)
            self.assertEqual(len(validate_vpk(path,'skin')),2)
            entries['scripts/items/items_game.txt']=b'forbidden item schema'
            write_single(path,entries)
            with self.assertRaises(ValueError):validate_vpk(path,'skin')

    def test_active_legacy_package_offers_rebuild_instead_of_deactivation(self):
        from desktop_ui import App
        from packages import CATALOG
        from types import SimpleNamespace
        item = next(p for p in CATALOG['heroes'] if p['hero']=='spectre')
        with tempfile.TemporaryDirectory() as folder:
            app=App.__new__(App)
            app.kind='skin';app.hero='spectre';app.busy=False;app.assets=Path(folder)
            app.library=SimpleNamespace(generated_skin=lambda *_:None,imported_skin=lambda *_:None)
            app.current={'slots':{'skin:spectre':{'id':item['id'],'sha256':item['sha256']}},'conflict':None}
            slot,selected=app.selected()
            self.assertTrue(selected['needs_rebuild'])
            calls=[];app.start_change=lambda *args:calls.append(args)
            app.toggle()
            self.assertFalse(calls[0][2])

    def test_legacy_import_does_not_mask_invalidated_generated_cache(self):
        from desktop_ui import App
        from packages import CATALOG
        from types import SimpleNamespace
        item = next(p for p in CATALOG['heroes'] if p['hero']=='skeleton_king')
        with tempfile.TemporaryDirectory() as folder:
            app=App.__new__(App)
            app.kind='skin';app.hero='skeleton_king';app.assets=Path(folder)
            app.library=SimpleNamespace(generated_skin=lambda *_:None,
                imported_skin=lambda *_:{**item, 'package_path':'legacy.vpk'})
            app.current={'slots':{},'conflict':None}
            _, selected=app.selected()
            self.assertTrue(selected['needs_rebuild'])
            self.assertFalse(selected['available'])
            self.assertNotIn('package_path',selected)


if __name__ == '__main__': unittest.main()
