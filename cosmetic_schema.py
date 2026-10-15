"""Read the official item schema; never modify item definitions or inventory."""
import re
import hashlib
import json

ASSEMBLY_REVISION = 3
INVISIBLE_MODEL = 'models/development/invisiblebox.vmdl_c'


def recipe_signature(recipe):
    return hashlib.sha256(json.dumps({'revision': ASSEMBLY_REVISION, 'recipe': recipe},
        sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()

TOKEN = re.compile(r'//[^\r\n]*|/\*.*?\*/|"(?:\\.|[^"\\])*"|[{}]|[^\s{}"]+', re.S)
FIELDS = {'prefab', 'item_slot', 'model_player', 'used_by_heroes', 'visuals', 'styles', 'name'}


def _tokens(text):
    for match in TOKEN.finditer(text):
        value = match.group()
        if value.startswith(('//', '/*')):
            continue
        if value.startswith('"'):
            yield re.sub(r'\\(["\\])', r'\1', value[1:-1])
        else:
            yield value


def _value(tokens, first, depth=0):
    if depth > 64:
        raise ValueError('Item schema nesting exceeds the supported depth.')
    if first != '{':
        return first
    result = {}
    for key in tokens:
        if key == '}':
            return result
        value = _value(tokens, next(tokens), depth+1)
        if key in result:
            previous = result[key]
            result[key] = previous+[value] if isinstance(previous, list) else [previous, value]
        else:
            result[key] = value
    raise ValueError('Incomplete item schema block.')


def _skip(tokens, first):
    if first != '{':
        return
    depth = 1
    for token in tokens:
        if token == '{': depth += 1
        elif token == '}': depth -= 1
        if not depth: return
    raise ValueError('Incomplete item schema section.')


def read_schema(data):
    """Keep item definitions and prefabs without retaining unrelated large sections."""
    tokens = iter(_tokens(data.decode('utf-8-sig') if isinstance(data, bytes) else data))
    if next(tokens) != 'items_game' or next(tokens) != '{':
        raise ValueError('Unsupported official item schema.')
    sections = {'items': {}, 'prefabs': {}}
    for section in tokens:
        if section == '}': break
        opening = next(tokens)
        if section not in sections:
            _skip(tokens, opening)
            continue
        if opening != '{': raise ValueError('Invalid item schema section.')
        for key in tokens:
            if key == '}': break
            value = _value(tokens, next(tokens))
            if isinstance(value, dict):
                sections[section][key] = {k: v for k, v in value.items() if k in FIELDS}
    if not sections['items']:
        raise ValueError('Official item schema contains no items.')
    return sections


def resolve_item(item, prefabs, chain=()):
    result = {}
    for name in str(item.get('prefab', '')).split():
        if name in chain: raise ValueError('Cyclic item prefab.')
        if name in prefabs:
            result.update(resolve_item(prefabs[name], prefabs, chain+(name,)))
    result.update(item)
    return result


def _model(value):
    if not isinstance(value, str): return None
    value = value.replace('\\', '/')
    if not value.startswith('models/') or not value.endswith('.vmdl') or '..' in value.split('/') or ':' in value:
        return None
    return value+'_c'


def _walk(node):
    if isinstance(node, dict):
        yield node
        for value in node.values(): yield from _walk(value)
    elif isinstance(node, list):
        for value in node: yield from _walk(value)


def item_model_owners(schema):
    owners = {}
    for raw in schema['items'].values():
        item = resolve_item(raw, schema['prefabs'])
        users = item.get('used_by_heroes', {})
        if not isinstance(users, dict): continue
        for node in _walk(item):
            paths = [_model(node.get('model_player'))]
            if node.get('type') in ('entity_model', 'model'):
                paths.append(_model(node.get('modifier')))
            for path in paths:
                if path: owners.setdefault(path, set()).update(users)
    return owners


def wearable_aliases(schema, hero, available_defaults, base_model=None, owners=None):
    """Map equipped wearable geometry to the same slot's already-built arcana piece."""
    unit = 'npc_dota_hero_'+hero
    if owners is None: owners = item_model_owners(schema)
    items = []
    for item_id, raw in schema['items'].items():
        item = resolve_item(raw, schema['prefabs'])
        users = item.get('used_by_heroes', {})
        if isinstance(users, dict) and unit in users:
            items.append((item_id, item))
    defaults, unsupported = {}, set()
    for _item_id, item in items:
        if 'default_item' not in str(item.get('prefab', '')).split(): continue
        slot, path = item.get('item_slot'), _model(item.get('model_player'))
        if slot and ('persona' in slot or slot == 'persona_selector'):
            unsupported.add(slot)
            continue
        if slot and not item.get('model_player'):
            path = INVISIBLE_MODEL
        if slot and path in available_defaults:
            defaults.setdefault(slot, set()).add(path)
    defaults = {slot: next(iter(paths)) for slot, paths in defaults.items() if len(paths) == 1}
    model_targets = {}
    for _item_id, item in items:
        target = defaults.get(item.get('item_slot'))
        if not target: continue
        for node in _walk(item):
            path = _model(node.get('model_player'))
            if path: model_targets.setdefault(path, set()).add(target)
    candidates, skipped = {}, []
    for item_id, item in items:
        users = item['used_by_heroes']
        if any(other != unit for other in users):
            skipped.append(item_id)
            continue
        for node in _walk(item):
            if (node.get('type') == 'entity_model' and node.get('asset') == unit
                    and base_model and 'persona' not in str(node.get('modifier', '')).lower()):
                source = _model(node.get('modifier'))
                if source and source != base_model:
                    candidates.setdefault(source, set()).add(base_model)
            target = defaults.get(item.get('item_slot'))
            if not target: continue
            source = _model(node.get('model_player'))
            if source and source != target and source not in defaults.values():
                candidates.setdefault(source, set()).add(target)
            # Some sets replace another wearable through a model modifier rather
            # than model_player (including style-specific replacements).
            if node.get('type') == 'model':
                source = _model(node.get('modifier'))
                asset = _model(node.get('asset'))
                if (source and asset and source != target and source not in defaults.values()
                        and owners.get(asset) == {unit}):
                    candidates.setdefault(source, set()).update(model_targets.get(asset, set()))
    # Ambiguous shared model paths cannot be assigned to a different slot safely.
    shared_models = sorted(source for source in candidates
        if not source.startswith(('models/items/', 'models/heroes/'))
        or any(other != unit for other in owners.get(source, set())))
    aliases = {source: next(iter(targets)) for source, targets in candidates.items()
               if len(targets) == 1 and source not in shared_models}
    ambiguous = sorted(source for source, targets in candidates.items() if len(targets) != 1)
    return aliases, {'slots': defaults, 'items': len(items), 'wearable_aliases': len(aliases),
                     'unsupported_persona_slots': sorted(unsupported),
                     'shared_or_generic_models_skipped': shared_models,
                     'ambiguous_models': ambiguous, 'shared_items_skipped': skipped}
