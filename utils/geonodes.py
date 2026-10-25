"""Geometry Nodes helpers for the linked add-on node groups and socket access."""
import os
import random
import re

import bpy

from .bake import AO_ATTRIBUTE_NAME


#----CONSTANTS----
_NODE_GROUPS_BLEND = os.path.join(
    os.path.dirname(__file__), "..", "resources", "node_groups.blend",
)
PROCEDURAL_NODE_GROUP_NAME = "gn_proceduralScatter_points"
INSTANCES_NODE_GROUP_NAME = "gn_proceduralScatter_instances"
MANUAL_POINTS_NODE_GROUP_NAME = "gn_manualScatter_points"
MANUAL_INSTANCES_NODE_GROUP_NAME = "gn_manualScatter_instances"
WIND_NODE_GROUP_NAME = "gn_windAnimation"
WIND_SOCKETS = ("Speed", "Power", "Scale", "Distortion", "Switch Direction")
WIND_LOCKED_SOCKETS = {"Random Rotation", "Align Surface"}
SURFACE_DEFORM_NAME_PREFIX = "Surface Deform"
EFFECTOR_NODE_GROUPS = {
    'MASK_BY_TEXTURE': "gn_effectorTexture",
    'MASK_BY_POSITION': "gn_effectorPosition",
    'MASK_BY_NORMAL': "gn_effectorSlope",
    'GEOMETRY_PROXIMITY': "gn_effectorProximity",
    'MASK_BY_ATTRIBUTE': "gn_effectorVertex",
    'MASK_BY_AO': "gn_effectorAO",
}
TEXTURE_MENU_OPTIONS = (
    ("Noise", {"Invert Color", "Level", "Seed", "Scale", "Detail", "Roughness"}),
    ("Voronoi", {"Invert Color", "Level", "Seed", "Scale", "Roughness"}),
    ("Wave", {
        "Invert Color", "Level", "Scale", "Detail", "Roughness",
        "Across", "Distortion", "Distortion Scale", "Offset",
    }),
    ("Image", {"Image", "Invert Color", "Level", "Scale UV"}),
)
TEXTURE_SOCKETS_BY_OPTION = dict(TEXTURE_MENU_OPTIONS)
TEXTURE_INTERNAL_SOCKETS = {"Texture", "UV"}
_EDGE_BLEND_SOCKETS = {"Value", "Seed", "Scale", "Detail", "Roughness"}
POSITION_BASE_SOCKETS = {"Axis", "Position", "Level", "Invert"}
POSITION_EDGE_BLEND_SOCKETS = set(_EDGE_BLEND_SOCKETS)
SLOPE_BASE_SOCKETS = {"Position", "Rotate X", "Rotate Y", "Invert"}
SLOPE_EDGE_BLEND_SOCKETS = set(_EDGE_BLEND_SOCKETS)
PROXIMITY_BASE_SOCKETS = {"Distance", "Invert"}
PROXIMITY_EDGE_BLEND_SOCKETS = set(_EDGE_BLEND_SOCKETS)
VERTEX_BASE_SOCKETS = {"Invert"}
VERTEX_EDGE_BLEND_SOCKETS = set(_EDGE_BLEND_SOCKETS)
AO_BASE_SOCKETS = {"Radius", "Invert"}
_UNBOUNDED_SEED_SPAN = 1_000_000
_UNBOUNDED_INT_SEED_RANGE = (0, 10000)
_FLOAT_SEED_LIMIT = 1000.0
USES_INPUT_STRUCTS = "properties" in bpy.types.NodesModifier.bl_rna.properties
_INPUT_STRUCT_FIELDS = ("type", "attribute_name", "layer_name", "value")
_NAME_SUFFIX_RE = re.compile(r"\.\d{3}$")


#----LIBRARY LINK----
def _norm_path(path):
    return os.path.normcase(os.path.abspath(bpy.path.abspath(path)))


def node_group_base_name(node_group):
    """Name of a node group without the .001 suffix Blender adds on a name clash."""
    return _NAME_SUFFIX_RE.sub("", node_group.name)


def get_node_groups_library():
    """The add-on's linked node_groups.blend in this file, or None."""
    target = _norm_path(_NODE_GROUPS_BLEND)
    for library in bpy.data.libraries:
        if _norm_path(library.filepath) == target:
            return library
    return None


def _link_node_groups(names):
    """Link node groups from the add-on library; linked groups cannot be edited in the file."""
    library = get_node_groups_library()
    result = {}
    if library is not None:
        for node_group in bpy.data.node_groups:
            if node_group.library == library and node_group.name in names:
                result[node_group.name] = node_group
    to_load = [name for name in names if name not in result]
    if not to_load:
        return result
    with bpy.data.libraries.load(_NODE_GROUPS_BLEND, link=True) as (data_from, data_to):
        missing = [name for name in to_load if name not in data_from.node_groups]
        if missing:
            raise RuntimeError(f"Node group(s) {missing} not found in {_NODE_GROUPS_BLEND}")
        data_to.node_groups = to_load
    for node_group in data_to.node_groups:
        result[node_group.name] = node_group
    return result


def _link_node_group(name):
    """Link a single node group."""
    return _link_node_groups([name])[name]


def relink_node_groups_library():
    """Point a library linked by another RAF Scatter install (other folder or Blender version)
    at this install's node_groups.blend; return True when a library was moved."""
    if get_node_groups_library() is not None:
        return False
    target = os.path.abspath(_NODE_GROUPS_BLEND)
    for library in bpy.data.libraries:
        if _is_addon_library_path(library.filepath):
            library.filepath = target
            library.reload()
            break
    else:
        return False
    for library in list(bpy.data.libraries):
        if _is_addon_library_path(library.filepath) and not _library_ids(library):
            bpy.data.libraries.remove(library)
    return True


def _is_addon_library_path(path):
    """True for the node_groups.blend of any RAF Scatter install."""
    parts = os.path.normcase(os.path.normpath(bpy.path.abspath(path))).split(os.sep)
    return len(parts) >= 3 and parts[-2:] == ["resources", "node_groups.blend"] and (
        parts[-3].startswith("raf_scatter")
    )


def _library_ids(library):
    """Every datablock of the file that comes from the given library."""
    ids = []
    for attribute in dir(bpy.data):
        if attribute.startswith("_") or attribute == "libraries":
            continue
        collection = getattr(bpy.data, attribute, None)
        if not isinstance(collection, bpy.types.bpy_prop_collection):
            continue
        ids += [
            idb for idb in collection
            if isinstance(idb, bpy.types.ID) and idb.library == library
        ]
    return ids


def count_linked_node_groups():
    library = get_node_groups_library()
    if library is None:
        return 0
    return sum(1 for node_group in bpy.data.node_groups if node_group.library == library)


def make_node_groups_local(show_inputs=False):
    """Make the linked RAF Scatter node groups (and what they use) local; return how many groups.
    show_inputs also shows every input in the modifier panel (the add-on hides most of them)."""
    library = get_node_groups_library()
    if library is None:
        return 0
    names = {
        node_group.name for node_group in bpy.data.node_groups if node_group.library == library
    }
    count = len(names)
    local_before = [
        node_group for node_group in bpy.data.node_groups
        if node_group.library is None and node_group_base_name(node_group) in names
    ]
    known = {node_group.as_pointer() for node_group in local_before}
    remaining = _library_ids(library)
    while remaining:
        for idb in remaining:
            idb.make_local()
        left = _library_ids(library)
        if len(left) == len(remaining):
            break
        remaining = left
    if not remaining:
        bpy.data.libraries.remove(library)
    _replace_older_local_copies(local_before, known, names)
    if show_inputs:
        for node_group in bpy.data.node_groups:
            if node_group.library is None and node_group_base_name(node_group) in names:
                _show_inputs_in_modifier(node_group)
    return count


def _replace_older_local_copies(local_before, known, names):
    """Hand the users and plain name of older local copies to the freshly made-local groups."""
    fresh = {
        node_group_base_name(node_group): node_group for node_group in bpy.data.node_groups
        if node_group.library is None and node_group.as_pointer() not in known
        and node_group_base_name(node_group) in names
    }
    for old in local_before:
        new = fresh.get(node_group_base_name(old))
        if new is None:
            continue
        old.user_remap(new)
        bpy.data.node_groups.remove(old)
    for base_name, node_group in fresh.items():
        node_group.name = base_name


def _show_inputs_in_modifier(node_group):
    for item in node_group.interface.items_tree:
        if item.item_type != 'SOCKET' or item.in_out != 'INPUT':
            continue
        if hasattr(item, "hide_in_modifier"):
            item.hide_in_modifier = False


#----MODIFIER STACK----
def _move_modifier(curve_obj, modifier, target_index):
    """Move a modifier to target_index if it is not already there."""
    current = curve_obj.modifiers.find(modifier.name)
    if current != target_index:
        curve_obj.modifiers.move(current, target_index)


def _is_surface_deform_modifier(modifier):
    """True for the native Surface Deform and its GeoNodes variant."""
    return (
        modifier.type == 'SURFACE_DEFORM'
        or (
            modifier.type == 'NODES'
            and modifier.node_group is not None
            and modifier.node_group.name.startswith(SURFACE_DEFORM_NAME_PREFIX)
        )
    )


def _deduplicate_surface_deform(curve_obj):
    """Collapse duplicate Surface Deform modifiers and stale node groups."""
    base_group = bpy.data.node_groups.get(SURFACE_DEFORM_NAME_PREFIX)
    surface_deform_mods = [
        mod for mod in curve_obj.modifiers if _is_surface_deform_modifier(mod)
    ]
    if not surface_deform_mods:
        return
    keeper = surface_deform_mods[0]
    if keeper.type == 'NODES' and base_group is not None:
        keeper.node_group = base_group
    for extra in surface_deform_mods[1:]:
        curve_obj.modifiers.remove(extra)
    for group in list(bpy.data.node_groups):
        if group.name.startswith(f"{SURFACE_DEFORM_NAME_PREFIX}.") and group.users == 0:
            bpy.data.node_groups.remove(group)


def _is_effector_modifier(modifier):
    """True if the modifier uses one of the addon effector node groups."""
    return (
        modifier.type == 'NODES'
        and modifier.node_group is not None
        and node_group_base_name(modifier.node_group) in EFFECTOR_NODE_GROUPS.values()
    )


def _effector_block_base(curve_obj):
    """Return the first stack slot effectors may occupy."""
    for group_name in (PROCEDURAL_NODE_GROUP_NAME, MANUAL_POINTS_NODE_GROUP_NAME):
        points = find_modifier_by_node_group(curve_obj, group_name)
        if points is not None:
            return curve_obj.modifiers.find(points.name) + 1
    for i, mod in enumerate(curve_obj.modifiers):
        if _is_surface_deform_modifier(mod):
            return i + 1
    return 0


def _effector_block_end(curve_obj):
    """Return the first stack slot below every effector."""
    end = _effector_block_base(curve_obj)
    for i, mod in enumerate(curve_obj.modifiers):
        if _is_effector_modifier(mod) and i + 1 > end:
            end = i + 1
    return end


def _cap_before_instances(curve_obj, index):
    """Cap an effector index so it stays above instances modifiers."""
    capped = index
    for group_name in (INSTANCES_NODE_GROUP_NAME, MANUAL_INSTANCES_NODE_GROUP_NAME):
        instances = find_modifier_by_node_group(curve_obj, group_name)
        if instances is not None:
            capped = min(capped, curve_obj.modifiers.find(instances.name))
    return capped


#----SOCKET ACCESS----
def _find_socket(node_tree, socket_name):
    """Find a socket by name in any direction."""
    for item in node_tree.interface.items_tree:
        if item.item_type == 'SOCKET' and item.name == socket_name:
            return item
    return None


def find_input_socket(node_tree, socket_name):
    """Find an INPUT socket by name."""
    for item in node_tree.interface.items_tree:
        if (
            item.item_type == 'SOCKET'
            and item.in_out == 'INPUT'
            and item.name == socket_name
        ):
            return item
    return None


def read_node_group_inputs(node_group):
    """Return name, identifier, type, default and range for every input socket."""
    inputs = []
    for item in node_group.interface.items_tree:
        if item.item_type != 'SOCKET' or item.in_out != 'INPUT':
            continue
        inputs.append({
            "name": item.name,
            "identifier": item.identifier,
            "socket_type": item.socket_type,
            "default_value": getattr(item, "default_value", None),
            "min_value": getattr(item, "min_value", None),
            "max_value": getattr(item, "max_value", None),
        })
    return inputs


def find_modifier_by_node_group(curve_obj, node_group_name):
    """Return the first NODES modifier using the named node group."""
    if curve_obj is None:
        return None
    for modifier in curve_obj.modifiers:
        if (
            modifier.type == 'NODES'
            and modifier.node_group is not None
            and node_group_base_name(modifier.node_group) == node_group_name
        ):
            return modifier
    return None


def get_procedural_modifier(system):
    """Procedural points modifier of a PROCEDURAL system."""
    if system is None or system.system_type != 'PROCEDURAL':
        return None
    return find_modifier_by_node_group(system.curve_obj, PROCEDURAL_NODE_GROUP_NAME)


def get_instances_modifier(system):
    """Instances modifier of a PROCEDURAL system."""
    if system is None or system.system_type != 'PROCEDURAL':
        return None
    return find_modifier_by_node_group(system.curve_obj, INSTANCES_NODE_GROUP_NAME)


def get_manual_points_modifier(system):
    """Points modifier of a MANUAL system."""
    if system is None or system.system_type != 'MANUAL':
        return None
    return find_modifier_by_node_group(system.curve_obj, MANUAL_POINTS_NODE_GROUP_NAME)


def get_manual_instances_modifier(system):
    """Instances modifier of a MANUAL system."""
    if system is None or system.system_type != 'MANUAL':
        return None
    return find_modifier_by_node_group(system.curve_obj, MANUAL_INSTANCES_NODE_GROUP_NAME)


def get_effector_modifier(system, effector):
    """Modifier mirrored by an effector list item."""
    if system is None or system.curve_obj is None:
        return None
    if not effector.modifier_name:
        return None
    return system.curve_obj.modifiers.get(effector.modifier_name)


#----SOCKET VALUE STORAGE----
def _input_struct(modifier, socket):
    """Return the per-socket input struct of a modifier (Blender 5.2+), or None."""
    return getattr(modifier.properties.inputs, socket.identifier, None)


def _menu_enum_items(struct):
    return struct.bl_rna.properties["value"].enum_items


def _has_input(modifier, socket):
    if USES_INPUT_STRUCTS:
        return _input_struct(modifier, socket) is not None
    return socket.identifier in modifier


def read_socket_value(modifier, socket, fallback=None):
    """Read the modifier value of an interface socket; Menu sockets give their item id."""
    if not USES_INPUT_STRUCTS:
        return modifier.get(socket.identifier, fallback)
    struct = _input_struct(modifier, socket)
    if struct is None or not hasattr(struct, "value"):
        return fallback
    value = struct.value
    if socket.socket_type == 'NodeSocketMenu':
        items = _menu_enum_items(struct)
        return items[value].value if value in items else fallback
    if hasattr(value, "__len__") and not isinstance(value, str):
        return list(value)
    return value


def _write_socket_value(modifier, socket, value):
    """Write a modifier socket value; Menu sockets take their item id. Return success."""
    if not USES_INPUT_STRUCTS:
        try:
            modifier[socket.identifier] = value
        except TypeError:
            del modifier[socket.identifier]
            modifier[socket.identifier] = value
        return True
    struct = _input_struct(modifier, socket)
    if struct is None or not hasattr(struct, "value"):
        return False
    if socket.socket_type == 'NodeSocketMenu' and isinstance(value, int):
        names = [item.identifier for item in _menu_enum_items(struct) if item.value == value]
        if not names:
            return False
        value = names[0]
    try:
        struct.value = value
    except (TypeError, ValueError, AttributeError):
        return False
    return True


def _copy_input_structs(source, target):
    """Copy every input value, mode and attribute name between two modifiers (5.2+)."""
    for socket in source.node_group.interface.items_tree:
        if socket.item_type != 'SOCKET' or socket.in_out != 'INPUT':
            continue
        src, dst = _input_struct(source, socket), _input_struct(target, socket)
        if src is None or dst is None:
            continue
        for field in _INPUT_STRUCT_FIELDS:
            if hasattr(src, field):
                try:
                    setattr(dst, field, getattr(src, field))
                except (TypeError, ValueError, AttributeError):
                    continue


#----SOCKET ACCESS----
def get_modifier_input_prop(modifier, socket_name):
    """Return (owner, property path) to draw a socket with layout.prop, or None."""
    if modifier is None or modifier.node_group is None:
        return None
    socket = find_input_socket(modifier.node_group, socket_name)
    if socket is None or not _has_input(modifier, socket):
        return None
    if USES_INPUT_STRUCTS:
        struct = _input_struct(modifier, socket)
        return (struct, "value") if hasattr(struct, "value") else None
    return modifier, f'["{socket.identifier}"]'


def get_modifier_input_value(modifier, socket_name, fallback=None):
    """Read a socket value from the modifier, or fallback."""
    if modifier is None or modifier.node_group is None:
        return fallback
    socket = find_input_socket(modifier.node_group, socket_name)
    if socket is None:
        return fallback
    return read_socket_value(modifier, socket, fallback)


def get_menu_socket_items(modifier, socket_name):
    """Return {item name: stored value} of a Menu socket; values are item ids, not positions."""
    if modifier is None or modifier.node_group is None:
        return {}
    socket = find_input_socket(modifier.node_group, socket_name)
    if socket is None or not _has_input(modifier, socket):
        return {}
    if USES_INPUT_STRUCTS:
        return {item.name: item.value for item in _menu_enum_items(_input_struct(modifier, socket))}
    try:
        items = modifier.id_properties_ui(socket.identifier).as_dict().get("items", ())
    except (TypeError, KeyError):
        return {}
    return {item[1]: item[4] for item in items}


def get_menu_socket_label(modifier, socket_name):
    """Return the name of the item currently stored in a Menu socket, or None."""
    value = get_modifier_input_value(modifier, socket_name)
    for name, item_value in get_menu_socket_items(modifier, socket_name).items():
        if item_value == value:
            return name
    return None


def set_modifier_input_value(modifier, socket_name, value):
    """Write a socket value by name and heal stale modifier keys."""
    if modifier is None or modifier.node_group is None:
        return False
    socket = find_input_socket(modifier.node_group, socket_name)
    if socket is None or not _write_socket_value(modifier, socket, value):
        return False
    modifier.id_data.update_tag()
    enabled = modifier.show_viewport
    modifier.show_viewport = not enabled
    modifier.show_viewport = enabled
    return True


def ensure_modifier_socket_defaults(modifier):
    """Materialize missing socket keys from node group defaults."""
    if modifier is None or modifier.node_group is None or USES_INPUT_STRUCTS:
        return
    for item in modifier.node_group.interface.items_tree:
        if item.item_type != 'SOCKET' or item.in_out != 'INPUT':
            continue
        if item.identifier in modifier:
            continue
        default = getattr(item, "default_value", None)
        if default is None:
            continue
        try:
            modifier[item.identifier] = default
        except (TypeError, OverflowError):
            continue


def ensure_system_modifier_defaults(system):
    """Run ensure_modifier_socket_defaults() on every modifier a system owns."""
    if system is None or system.curve_obj is None:
        return
    ensure_modifier_socket_defaults(get_procedural_modifier(system))
    ensure_modifier_socket_defaults(get_manual_points_modifier(system))
    ensure_modifier_socket_defaults(get_instances_modifier(system))
    ensure_modifier_socket_defaults(get_manual_instances_modifier(system))
    for effector in system.effectors:
        ensure_modifier_socket_defaults(get_effector_modifier(system, effector))


def randomize_seed(modifier, socket_name="Seed"):
    """Write a random value inside the socket range; return False if the socket is missing."""
    if modifier is None or modifier.node_group is None:
        return False
    socket = find_input_socket(modifier.node_group, socket_name)
    if socket is None:
        return False
    if socket.socket_type == 'NodeSocketInt':
        low, high = socket.min_value, socket.max_value
        if high - low > _UNBOUNDED_SEED_SPAN:
            low, high = _UNBOUNDED_INT_SEED_RANGE
        value = random.randint(low, high)
    else:
        low = max(socket.min_value, -_FLOAT_SEED_LIMIT)
        high = min(socket.max_value, _FLOAT_SEED_LIMIT)
        value = round(random.uniform(low, high), 2)
    return set_modifier_input_value(modifier, socket_name, value)


#----EFFECTOR MODIFIERS----
def _wire_texture_uv(modifier, target_ground):
    """Wire the UV socket from the target ground."""
    socket = find_input_socket(modifier.node_group, "UV")
    if socket is None or target_ground is None:
        return
    if socket.socket_type == 'NodeSocketObject':
        _write_socket_value(modifier, socket, target_ground)
    elif socket.socket_type == 'NodeSocketString':
        uv_layers = target_ground.data.uv_layers
        if uv_layers.active is not None:
            _write_socket_value(modifier, socket, uv_layers.active.name)


def _wire_vertex_ground(modifier, target_ground):
    """Wire the vertex mask target ground socket."""
    if target_ground is None:
        return
    socket = find_input_socket(modifier.node_group, "Target Ground")
    if socket is not None:
        _write_socket_value(modifier, socket, target_ground)


def wire_ao_ground(modifier, target_ground):
    """Point the AO mask at the target ground and its baked color attribute."""
    if target_ground is None or modifier is None or modifier.node_group is None:
        return
    for socket_name, value in (("Object", target_ground), ("Attribute", AO_ATTRIBUTE_NAME)):
        socket = find_input_socket(modifier.node_group, socket_name)
        if socket is not None:
            _write_socket_value(modifier, socket, value)


def get_effector_node_group(effector_type):
    """Append and return the node group registered for an effector type."""
    group_name = EFFECTOR_NODE_GROUPS.get(effector_type)
    if group_name is None:
        return None
    return _link_node_group(group_name)


def append_effector_to_stack(curve_obj, effector_type, modifier_name, target_ground=None):
    """Create an effector modifier at the top of the effector block."""
    node_group = get_effector_node_group(effector_type)
    if node_group is None:
        return None
    modifier = curve_obj.modifiers.new(name=modifier_name, type='NODES')
    modifier.node_group = node_group
    ensure_modifier_socket_defaults(modifier)
    if effector_type == 'MASK_BY_TEXTURE':
        _wire_texture_uv(modifier, target_ground)
    elif effector_type == 'MASK_BY_ATTRIBUTE':
        _wire_vertex_ground(modifier, target_ground)
    elif effector_type == 'MASK_BY_AO':
        wire_ao_ground(modifier, target_ground)
    _move_modifier(
        curve_obj, modifier,
        _cap_before_instances(curve_obj, _effector_block_base(curve_obj)),
    )
    return modifier


def remove_effector_modifier(system, effector):
    """Remove the effector's modifier; returns False if none exists."""
    modifier = get_effector_modifier(system, effector)
    if modifier is None:
        return False
    system.curve_obj.modifiers.remove(modifier)
    return True


def duplicate_effector_modifier(curve_obj, modifier):
    """Copy an effector modifier with all socket values to the top of the effector block."""
    new_modifier = curve_obj.modifiers.new(name=modifier.name, type='NODES')
    new_modifier.node_group = modifier.node_group
    if USES_INPUT_STRUCTS:
        _copy_input_structs(modifier, new_modifier)
    else:
        for key in modifier.keys():
            new_modifier[key] = modifier[key]
    ensure_modifier_socket_defaults(new_modifier)
    _move_modifier(
        curve_obj, new_modifier,
        _cap_before_instances(curve_obj, _effector_block_base(curve_obj)),
    )
    return new_modifier


def resync_effector_modifier_links(system):
    """Re-link effector items whose modifier was renamed outside the addon."""
    if system is None or system.curve_obj is None:
        return
    curve_obj = system.curve_obj
    modifiers = curve_obj.modifiers
    stale = []
    for effector in system.effectors:
        if effector.curve_obj is None:
            effector.curve_obj = curve_obj
        if not effector.modifier_name or modifiers.get(effector.modifier_name) is None:
            stale.append(effector)
    if not stale:
        return
    claimed = {
        effector.modifier_name for effector in system.effectors
        if effector.modifier_name and modifiers.get(effector.modifier_name) is not None
    }
    unclaimed = [
        modifier for modifier in modifiers
        if _is_effector_modifier(modifier) and modifier.name not in claimed
    ]
    if len(unclaimed) != len(stale):
        return
    for effector, modifier in zip(stale, unclaimed):
        effector.modifier_name = modifier.name
        if effector.name != modifier.name:
            effector.name = modifier.name


#----INSTANCES MODIFIERS----
def _add_instances_modifier(curve_obj, group_name):
    """Create an instances modifier directly below the effector block."""
    node_group = _link_node_group(group_name)
    modifier = curve_obj.modifiers.new(name=group_name, type='NODES')
    modifier.node_group = node_group
    ensure_modifier_socket_defaults(modifier)
    _move_modifier(curve_obj, modifier, _effector_block_end(curve_obj))
    _keep_animation_last(curve_obj)
    return modifier


def _remove_instances_modifier(curve_obj, group_name):
    """Remove an instances modifier."""
    modifier = find_modifier_by_node_group(curve_obj, group_name)
    if modifier is None:
        return False
    curve_obj.modifiers.remove(modifier)
    return True


def _apply_instances_assignment(system, group_name, mode, obj, collection):
    """Write a cached instance assignment onto an instances modifier."""
    if system is None or system.curve_obj is None:
        return
    modifier = find_modifier_by_node_group(system.curve_obj, group_name)
    if modifier is None:
        return
    set_modifier_input_value(modifier, "Instances", mode)
    if obj is not None:
        set_modifier_input_value(modifier, "Object", obj)
    if collection is not None:
        set_modifier_input_value(modifier, "Collection", collection)


def add_instances_modifier(curve_obj):
    """Create the procedural instances modifier below the effector block."""
    return _add_instances_modifier(curve_obj, INSTANCES_NODE_GROUP_NAME)


def remove_instances_modifier(curve_obj):
    """Remove the procedural instances modifier."""
    return _remove_instances_modifier(curve_obj, INSTANCES_NODE_GROUP_NAME)


def apply_instances_assignment(system):
    """Write the cached procedural assignment onto its instances modifier."""
    if system is None:
        return
    _apply_instances_assignment(
        system, INSTANCES_NODE_GROUP_NAME,
        system.instances_mode, system.instances_object, system.instances_collection,
    )


def add_manual_instances_modifier(curve_obj):
    """Create the manual instances modifier below the effector block."""
    return _add_instances_modifier(curve_obj, MANUAL_INSTANCES_NODE_GROUP_NAME)


def remove_manual_instances_modifier(curve_obj):
    """Remove the manual instances modifier."""
    return _remove_instances_modifier(curve_obj, MANUAL_INSTANCES_NODE_GROUP_NAME)


def apply_manual_instances_assignment(system):
    """Write the cached manual assignment onto its instances modifier."""
    if system is None:
        return
    _apply_instances_assignment(
        system, MANUAL_INSTANCES_NODE_GROUP_NAME,
        system.manual_instances_mode,
        system.manual_instances_object,
        system.manual_instances_collection,
    )


#----ANIMATION MODIFIERS----
def get_system_instances_modifier(system):
    """The instances modifier of a system of either type."""
    if system is None:
        return None
    if system.system_type == 'MANUAL':
        return get_manual_instances_modifier(system)
    return get_instances_modifier(system)


def get_wind_modifier(system):
    if system is None or system.curve_obj is None:
        return None
    return find_modifier_by_node_group(system.curve_obj, WIND_NODE_GROUP_NAME)


def _keep_animation_last(curve_obj):
    """Animation acts on the finished instances, so it sits right below the instances modifier
    (Blender 5.2 keeps its own Hair Dynamics modifier at the very end)."""
    modifier = find_modifier_by_node_group(curve_obj, WIND_NODE_GROUP_NAME)
    if modifier is None:
        return
    for group_name in (INSTANCES_NODE_GROUP_NAME, MANUAL_INSTANCES_NODE_GROUP_NAME):
        instances = find_modifier_by_node_group(curve_obj, group_name)
        if instances is not None:
            target = curve_obj.modifiers.find(instances.name)
            if curve_obj.modifiers.find(modifier.name) < target:
                target -= 1
            _move_modifier(curve_obj, modifier, target + 1)
            return
    _move_modifier(curve_obj, modifier, len(curve_obj.modifiers) - 1)


def enable_wind(system):
    """Add the wind modifier; Random Rotation and Align Surface are overridden and their values
    kept on the system for disable_wind(). Return the modifier, or None without instances."""
    instances = get_system_instances_modifier(system)
    if instances is None or get_wind_modifier(system) is not None:
        return None
    system.wind_saved_rotation = tuple(
        get_modifier_input_value(instances, "Random Rotation", (0.0, 0.0, 0.0))
    )
    system.wind_saved_align = bool(get_modifier_input_value(instances, "Align Surface", False))
    set_modifier_input_value(instances, "Random Rotation", (0.0, 0.0, 0.0))
    set_modifier_input_value(instances, "Align Surface", False)
    curve_obj = system.curve_obj
    modifier = curve_obj.modifiers.new(name=WIND_NODE_GROUP_NAME, type='NODES')
    modifier.node_group = _link_node_group(WIND_NODE_GROUP_NAME)
    ensure_modifier_socket_defaults(modifier)
    reset_wind(modifier)
    _keep_animation_last(curve_obj)
    return modifier


def reset_wind(modifier):
    """Write the node group's own default into every wind setting."""
    for socket_name in WIND_SOCKETS:
        socket = find_input_socket(modifier.node_group, socket_name)
        if socket is not None:
            set_modifier_input_value(modifier, socket_name, socket.default_value)


def read_wind_settings(modifier):
    """The wind settings as plain values, for the wind clipboard."""
    settings = {}
    for socket_name in WIND_SOCKETS:
        value = get_modifier_input_value(modifier, socket_name)
        if isinstance(value, (bool, int, float)):
            settings[socket_name] = value
    return settings


def write_wind_settings(modifier, settings):
    for socket_name in WIND_SOCKETS:
        if socket_name in settings:
            set_modifier_input_value(modifier, socket_name, settings[socket_name])


def disable_wind(system):
    """Remove the wind modifier and give the instances their own rotation values back."""
    modifier = get_wind_modifier(system)
    if modifier is None:
        return False
    system.curve_obj.modifiers.remove(modifier)
    instances = get_system_instances_modifier(system)
    set_modifier_input_value(instances, "Random Rotation", tuple(system.wind_saved_rotation))
    set_modifier_input_value(instances, "Align Surface", system.wind_saved_align)
    return True


#----SYSTEM SETUP----
def setup_system_modifier_stack(curve_obj, system_type, target_ground):
    """Create the points-stage modifier for a system and wire its target."""
    _deduplicate_surface_deform(curve_obj)
    if system_type == 'MANUAL':
        node_group = _link_node_group(MANUAL_POINTS_NODE_GROUP_NAME)
        modifier = curve_obj.modifiers.new(name=MANUAL_POINTS_NODE_GROUP_NAME, type='NODES')
        modifier.node_group = node_group
        ensure_modifier_socket_defaults(modifier)
        return modifier
    node_groups = _link_node_groups([PROCEDURAL_NODE_GROUP_NAME, INSTANCES_NODE_GROUP_NAME])
    node_group = node_groups[PROCEDURAL_NODE_GROUP_NAME]
    modifier = curve_obj.modifiers.new(name=PROCEDURAL_NODE_GROUP_NAME, type='NODES')
    modifier.node_group = node_group
    ensure_modifier_socket_defaults(modifier)
    target_socket = _find_socket(node_group, "Target Ground")
    if target_socket is not None:
        _write_socket_value(modifier, target_socket, target_ground)
    return modifier


def duplicate_system_curve(curve_obj):
    """Copy a system's curve object (data + modifiers) into the same collections."""
    new_obj = curve_obj.copy()
    new_obj.data = curve_obj.data.copy()
    for collection in curve_obj.users_collection:
        collection.objects.link(new_obj)
    return new_obj
