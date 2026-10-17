"""Biome presets: serialize a ground's scatter systems and the .rafbiome file format."""
import datetime
import json
import os
import re

import bpy

from ..properties import VERTEX_MASK_GROUP_PREFIX, is_pickable_mesh
from . import geonodes as geonodes_utils
from . import thumbnails


#----CONSTANTS----
BIOME_FORMAT = 1
BIOME_KIND = "raf_scatter_biome"
BIOME_EXTENSION = ".rafbiome"
THUMBNAIL_EXTENSIONS = (".png", ".jpg", ".jpeg")
PACK_BIOME_SUBDIR = "biomes"
_BIOME_SUBDIR = "presets/raf_scatter/biomes"
_PACK_SUBDIR = "presets/raf_scatter/packs"
_KEY_SEPARATOR = "/"
_PACK_SOURCE_SEPARATOR = "::"
_EFFECTOR_REF_SOCKETS = {"Object", "Collection", "Image", "Attribute", "Target Ground", "UV"}
_POINTS_SKIP_SOCKETS = {"Target Ground"}
_INSTANCES_SKIP_SOCKETS = {"Instances", "Object", "Collection"}
_RENAMED_SOCKETS = {"Z Position": "Position"}
_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


#----BIOME FILES----
def _user_folder(subdir):
    folder = bpy.utils.user_resource('SCRIPTS', path=subdir, create=True)
    return os.path.normpath(folder) if folder else ""


def get_biome_dir():
    """Return Blender's user presets folder for biomes, creating it when missing."""
    return _user_folder(_BIOME_SUBDIR)


def get_packs_dir():
    """Return the folder installed biome packs live in, creating it when missing."""
    return _user_folder(_PACK_SUBDIR)


def sanitize_biome_name(name):
    """Return a file-safe biome name, or an empty string."""
    return _INVALID_FILENAME_CHARS.sub("_", name).strip().strip(".")


def make_biome_key(pack_id, name):
    """Return the library key of a biome: its name, prefixed by its pack when it has one."""
    return f"{pack_id}{_KEY_SEPARATOR}{name}" if pack_id else name


def split_biome_key(key):
    """Return (pack id or '', biome name) of a biome key."""
    pack_id, _separator, name = key.rpartition(_KEY_SEPARATOR)
    return pack_id, name


def get_pack_root(key):
    """Return the install folder of the pack a biome comes from, or None for a saved biome."""
    pack_id, _name = split_biome_key(key)
    return os.path.join(get_packs_dir(), pack_id) if pack_id else None


def _biome_folder(key):
    pack_root = get_pack_root(key)
    return os.path.join(pack_root, PACK_BIOME_SUBDIR) if pack_root else get_biome_dir()


def get_biome_path(key):
    _pack_id, name = split_biome_key(key)
    return os.path.join(_biome_folder(key), sanitize_biome_name(name) + BIOME_EXTENSION)


def biome_exists(name):
    safe_name = sanitize_biome_name(name)
    return bool(safe_name) and os.path.isfile(get_biome_path(safe_name))


def find_thumbnail(key):
    """Return the thumbnail file stored beside a biome, or None."""
    _pack_id, name = split_biome_key(key)
    for extension in THUMBNAIL_EXTENSIONS:
        path = os.path.join(_biome_folder(key), sanitize_biome_name(name) + extension)
        if os.path.isfile(path):
            return path
    return None


def _biome_names(folder):
    if not folder or not os.path.isdir(folder):
        return []
    names = [
        os.path.splitext(entry)[0] for entry in os.listdir(folder)
        if entry.lower().endswith(BIOME_EXTENSION)
    ]
    return sorted(names, key=str.lower)


def list_biomes():
    """Return (name, thumbnail path or None) for every saved biome, sorted by name."""
    return [(name, find_thumbnail(name)) for name in _biome_names(get_biome_dir())]


def list_pack_biomes(pack_id):
    """Return (key, thumbnail path or None) for every biome of an installed pack."""
    folder = os.path.join(get_packs_dir(), pack_id, PACK_BIOME_SUBDIR)
    keys = [make_biome_key(pack_id, name) for name in _biome_names(folder)]
    return [(key, find_thumbnail(key)) for key in keys]


def resolve_pack_path(pack_root, relative_path):
    """Return the absolute path of a file inside a pack, or None when it points outside it."""
    if not isinstance(relative_path, str) or not relative_path:
        return None
    root = os.path.normpath(pack_root)
    path = os.path.normpath(os.path.join(root, *relative_path.split("/")))
    try:
        inside = os.path.commonpath([os.path.normcase(root), os.path.normcase(path)])
    except ValueError:
        return None
    return path if inside == os.path.normcase(root) else None


def resolve_pack_source(pack_root, pack_source):
    """Return the library source key of a pack asset reference, or None."""
    if not isinstance(pack_source, str):
        return None
    relative_path, _separator, name = pack_source.rpartition(_PACK_SOURCE_SEPARATOR)
    path = resolve_pack_path(pack_root, relative_path)
    return f"{path}{_PACK_SOURCE_SEPARATOR}{name}" if path and name else None


def write_biome(name, data):
    with open(get_biome_path(name), "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)


def _replace_thumbnail(name, write):
    """Write a new square PNG thumbnail with write(path), then drop older ones of the biome."""
    target = os.path.join(get_biome_dir(), sanitize_biome_name(name) + ".png")
    partial = target + ".part.png"
    try:
        write(partial)
        for extension in THUMBNAIL_EXTENSIONS:
            old = os.path.splitext(target)[0] + extension
            if old != target and os.path.isfile(old):
                os.remove(old)
        os.replace(partial, target)
    finally:
        if os.path.isfile(partial):
            os.remove(partial)


def save_thumbnail(name, source_path):
    """Store a 1:1 centre crop of an image as the biome thumbnail, replacing any older one."""
    extension = os.path.splitext(source_path)[1].lower()
    if extension not in THUMBNAIL_EXTENSIONS or not os.path.isfile(source_path):
        raise ValueError("thumbnail must be a .png or .jpg file")
    _replace_thumbnail(name, lambda path: thumbnails.write_square_png(source_path, path))


def capture_thumbnail(context, name):
    """Store a square viewport render as the biome thumbnail; raise RuntimeError on failure."""
    _replace_thumbnail(name, lambda path: thumbnails.capture_viewport(context, path))


def _validate_biome(data):
    """Raise ValueError when biome data does not match the known format."""
    if not isinstance(data, dict) or data.get("kind") != BIOME_KIND:
        raise ValueError("not a RAF Scatter biome")
    if data.get("format") != BIOME_FORMAT:
        raise ValueError("unknown biome format")
    systems = data.get("systems")
    if not isinstance(systems, list):
        raise ValueError("missing system list")
    for system in systems:
        if not isinstance(system, dict) or system.get("system_type") not in ('MANUAL', 'PROCEDURAL'):
            raise ValueError("invalid system entry")
        if not isinstance(system.get("points", {}), dict):
            raise ValueError("invalid distribution values")
        instances = system.get("instances")
        if instances is not None and not isinstance(instances, dict):
            raise ValueError("invalid instances entry")
        effectors = system.get("effectors", [])
        if not isinstance(effectors, list):
            raise ValueError("invalid effector list")
        for entry in effectors:
            if not isinstance(entry, dict) or not isinstance(entry.get("type"), str):
                raise ValueError("invalid effector entry")
            if not isinstance(entry.get("sockets", {}), dict):
                raise ValueError("invalid effector values")
            if not isinstance(entry.get("refs", {}), dict):
                raise ValueError("invalid effector references")


def read_biome(name):
    """Load and validate a biome file; raise ValueError on any problem."""
    try:
        with open(get_biome_path(name), "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(str(error)) from error
    _validate_biome(data)
    return data


#----BIOME MANAGEMENT----
def _timestamp():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _file_timestamp(path):
    return datetime.datetime.fromtimestamp(os.path.getmtime(path)).isoformat(timespec="seconds")


def read_biome_info(name):
    """Return display info for a saved biome without raising on a broken file."""
    path = get_biome_path(name)
    info = {
        "name": name, "description": "", "created": "", "modified": "",
        "manual": 0, "procedural": 0, "file_path": path, "valid": True,
    }
    try:
        data = read_biome(name)
    except ValueError:
        info["valid"] = False
        info["modified"] = _file_timestamp(path) if os.path.isfile(path) else ""
        return info
    systems = data["systems"]
    info["description"] = str(data.get("description", ""))
    info["created"] = str(data.get("created") or _file_timestamp(path))
    info["modified"] = str(data.get("modified") or info["created"])
    info["manual"] = sum(1 for system in systems if system["system_type"] == 'MANUAL')
    info["procedural"] = len(systems) - info["manual"]
    return info


def stamp_biome(data, description, previous=None):
    """Add description and dates to new biome data, keeping the original creation date."""
    now = _timestamp()
    data["description"] = description
    data["created"] = (previous or {}).get("created") or now
    data["modified"] = now
    data["blender_version"] = bpy.app.version_string
    return data


def rename_biome(old_name, new_name):
    """Rename a biome file and its thumbnail; raise ValueError when not possible."""
    safe_name = sanitize_biome_name(new_name)
    if not safe_name:
        raise ValueError("enter a name")
    if safe_name == old_name:
        return safe_name
    if biome_exists(safe_name):
        raise ValueError(f"a biome named \"{safe_name}\" already exists")
    try:
        data = read_biome(old_name)
    except ValueError:
        data = None
    thumbnail = find_thumbnail(old_name)
    os.replace(get_biome_path(old_name), get_biome_path(safe_name))
    if thumbnail is not None:
        extension = os.path.splitext(thumbnail)[1]
        os.replace(thumbnail, os.path.join(get_biome_dir(), safe_name + extension))
    if data is not None:
        data["name"] = safe_name
        data["modified"] = _timestamp()
        write_biome(safe_name, data)
    return safe_name


def delete_biome(name):
    """Delete a biome file and its thumbnail."""
    thumbnail = find_thumbnail(name)
    path = get_biome_path(name)
    if os.path.isfile(path):
        os.remove(path)
    if thumbnail is not None:
        os.remove(thumbnail)


#----SERIALIZE----
def _to_json_value(value):
    if hasattr(value, "to_list"):
        return value.to_list()
    if isinstance(value, list):
        return value
    if isinstance(value, (bool, int, float, str)):
        return value
    return None


def _serialize_sockets(modifier, skip):
    """Return every input socket value by name, except the skipped names."""
    sockets = {}
    if modifier is None or modifier.node_group is None:
        return sockets
    for item in modifier.node_group.interface.items_tree:
        if item.item_type != 'SOCKET' or item.in_out != 'INPUT' or item.name in skip:
            continue
        value = _to_json_value(geonodes_utils.read_socket_value(modifier, item))
        if value is not None:
            sockets[item.name] = value
    return sockets


def _serialize_effector_refs(effector, modifier):
    """Return the name-only references an effector depends on."""
    refs = {}
    if effector.effector_type == 'GEOMETRY_PROXIMITY':
        if effector.proximity_object is not None:
            refs["proximity_object"] = effector.proximity_object.name
        if effector.proximity_collection is not None:
            refs["proximity_collection"] = effector.proximity_collection.name
    elif effector.effector_type == 'MASK_BY_ATTRIBUTE':
        refs["vertex_mode"] = effector.vertex_mode
        if effector.vertex_mode == 1 and effector.vertex_group_name:
            refs["vertex_group"] = effector.vertex_group_name
    elif effector.effector_type == 'MASK_BY_TEXTURE':
        image = geonodes_utils.get_modifier_input_value(modifier, "Image")
        if isinstance(image, bpy.types.Image):
            refs["image"] = image.name
            if image.filepath:
                refs["image_filepath"] = bpy.path.abspath(image.filepath)
    return refs


def _serialize_effector(system, effector):
    modifier = geonodes_utils.get_effector_modifier(system, effector)
    if modifier is None or modifier.node_group is None:
        return None
    return {
        "type": effector.effector_type,
        "name": effector.name,
        "visible_viewport": modifier.show_viewport,
        "visible_render": modifier.show_render,
        "sockets": _serialize_sockets(modifier, _EFFECTOR_REF_SOCKETS),
        "refs": _serialize_effector_refs(effector, modifier),
    }


def _serialize_instances(system, describe_asset):
    """Return the instances block of a system, or None when instances are off."""
    if system.system_type == 'MANUAL':
        modifier = geonodes_utils.get_manual_instances_modifier(system)
        mode = system.manual_instances_mode
        obj, collection = system.manual_instances_object, system.manual_instances_collection
    else:
        modifier = geonodes_utils.get_instances_modifier(system)
        mode = system.instances_mode
        obj, collection = system.instances_object, system.instances_collection
    if modifier is None:
        return None
    return {
        "mode": mode,
        "sockets": _serialize_sockets(modifier, _INSTANCES_SKIP_SOCKETS),
        "object": describe_asset(obj) if obj is not None else None,
        "collection": describe_asset(collection) if collection is not None else None,
    }


def _serialize_system(system, describe_asset):
    curve_obj = system.curve_obj
    effectors = [_serialize_effector(system, effector) for effector in system.effectors]
    return {
        "system_type": system.system_type,
        "name": system.name,
        "hide_viewport": curve_obj.hide_viewport,
        "hide_render": curve_obj.hide_render,
        "points": _serialize_sockets(
            geonodes_utils.get_procedural_modifier(system), _POINTS_SKIP_SOCKETS,
        ),
        "instances": _serialize_instances(system, describe_asset),
        "effectors": [entry for entry in effectors if entry],
    }


def serialize_ground(ground, name, describe_asset):
    """Return every scatter system of a ground as biome data, index 0 first."""
    systems = [
        _serialize_system(system, describe_asset)
        for system in ground.scatter_systems if system.curve_obj is not None
    ]
    return {"format": BIOME_FORMAT, "kind": BIOME_KIND, "name": name, "systems": systems}


#----APPLY----
def _value_kind(value):
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "str"
    if isinstance(value, list) or hasattr(value, "to_list"):
        return "list"
    return None


def _coerce_socket_value(current, value):
    """Return the value matched to the stored socket type, or None if incompatible."""
    if current is None:
        return value
    if _value_kind(current) != _value_kind(value):
        return None
    if isinstance(current, float) and not isinstance(value, float):
        return float(value)
    if isinstance(current, int) and not isinstance(current, bool) and isinstance(value, float):
        return int(value)
    return value


def apply_sockets(modifier, sockets):
    """Write stored socket values by name, skipping values of the wrong type."""
    if modifier is None:
        return
    for socket_name, value in sockets.items():
        socket_name = _RENAMED_SOCKETS.get(socket_name, socket_name)
        current = geonodes_utils.get_modifier_input_value(modifier, socket_name)
        value = _coerce_socket_value(current, value)
        if value is not None:
            geonodes_utils.set_modifier_input_value(modifier, socket_name, value)


def _collection_in_scene(scene, collection):
    return any(child == collection for child in scene.collection.children_recursive)


def find_scene_object(scene, name):
    obj = bpy.data.objects.get(name) if name else None
    return obj if is_pickable_mesh(obj) else None


def find_scene_collection(scene, name):
    collection = bpy.data.collections.get(name) if name else None
    if collection is None or not _collection_in_scene(scene, collection):
        return None
    return collection


def _resolve_image(refs, pack_root):
    """Load the referenced image from its pack or stored file, else find it by name."""
    if pack_root is not None:
        filepath = resolve_pack_path(pack_root, refs.get("pack_image"))
    else:
        image = bpy.data.images.get(refs["image"])
        if image is not None:
            return image
        filepath = refs.get("image_filepath")
    if not filepath or not os.path.isfile(filepath):
        return bpy.data.images.get(refs["image"])
    try:
        return bpy.data.images.load(filepath, check_existing=True)
    except RuntimeError:
        return None


def _apply_vertex_refs(system, effector, refs, unresolved):
    """Restore the vertex mask source mode and its group on the target ground."""
    ground = system.target_ground
    groups = ground.vertex_groups if ground is not None else None
    if refs["vertex_mode"] == 1:
        effector.vertex_mode = 1
        group_name = refs.get("vertex_group")
        if not group_name:
            return
        if groups is not None and groups.get(group_name) is not None:
            effector.vertex_group_name = group_name
        else:
            unresolved.append(group_name)
        return
    effector.vertex_mode = 0
    if groups is None:
        return
    own_group = VERTEX_MASK_GROUP_PREFIX + ground.name
    if groups.get(own_group) is not None:
        effector.vertex_group_name = own_group


def _apply_effector_refs(system, effector, modifier, refs, scene, pack_root):
    """Resolve effector references by name and return the names left empty."""
    unresolved = []
    if "proximity_object" in refs:
        obj = find_scene_object(scene, refs["proximity_object"])
        if obj is not None:
            effector.proximity_object = obj
        else:
            unresolved.append(refs["proximity_object"])
    if "proximity_collection" in refs:
        collection = find_scene_collection(scene, refs["proximity_collection"])
        if collection is not None:
            effector.proximity_collection = collection
        else:
            unresolved.append(refs["proximity_collection"])
    if "vertex_mode" in refs:
        _apply_vertex_refs(system, effector, refs, unresolved)
    if "image" in refs:
        image = _resolve_image(refs, pack_root)
        if image is not None:
            geonodes_utils.set_modifier_input_value(modifier, "Image", image)
        else:
            unresolved.append(refs["image"])
    return unresolved


#----EFFECTOR CLIPBOARD----
def make_effector_clipboard(system, effectors):
    """Return clipboard JSON holding copies of the given effectors, in stack order."""
    entries = [_serialize_effector(system, effector) for effector in effectors]
    return json.dumps({
        "source": system.name,
        "copied": _timestamp(),
        "effectors": [entry for entry in entries if entry],
    })


def read_effector_clipboard(text):
    """Return the clipboard dict, or None when it is empty or not readable."""
    try:
        data = json.loads(text) if text else None
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or not isinstance(data.get("effectors"), list):
        return None
    entries = [
        entry for entry in data["effectors"]
        if isinstance(entry, dict) and isinstance(entry.get("type"), str)
    ]
    return {**data, "effectors": entries} if entries else None


def apply_effector_entry(system, effector, entry, scene, pack_root=None):
    """Write a stored effector onto a freshly created one; return unresolved names."""
    modifier = geonodes_utils.get_effector_modifier(system, effector)
    if modifier is None:
        return []
    apply_sockets(modifier, entry.get("sockets", {}))
    refs = entry.get("refs", {})
    unresolved = _apply_effector_refs(system, effector, modifier, refs, scene, pack_root)
    name = entry.get("name")
    if isinstance(name, str) and name:
        effector.name = name
    modifier.show_viewport = bool(entry.get("visible_viewport", True))
    modifier.show_render = bool(entry.get("visible_render", True))
    return unresolved
