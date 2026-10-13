"""Geometry Nodes helpers for local-copy node groups and socket access."""
import os
import random

import bpy


#----CONSTANTS----
_NODE_GROUPS_BLEND = os.path.join(
    os.path.dirname(__file__), "..", "resources", "node_groups.blend",
)
PROCEDURAL_NODE_GROUP_NAME = "gn_proceduralScatter_points"
INSTANCES_NODE_GROUP_NAME = "gn_proceduralScatter_instances"
MANUAL_POINTS_NODE_GROUP_NAME = "gn_manualScatter_points"
MANUAL_INSTANCES_NODE_GROUP_NAME = "gn_manualScatter_instances"
SURFACE_DEFORM_NAME_PREFIX = "Surface Deform"
EFFECTOR_NODE_GROUPS = {
    'MASK_BY_TEXTURE': "gn_effectorTexture",
    'MASK_BY_POSITION': "gn_effectorPosition",
    'MASK_BY_NORMAL': "gn_effectorSlope",
    'GEOMETRY_PROXIMITY': "gn_effectorProximity",
    'MASK_BY_ATTRIBUTE': "gn_effectorVertex",
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
_UNBOUNDED_SEED_SPAN = 1_000_000
_UNBOUNDED_INT_SEED_RANGE = (0, 10000)
_FLOAT_SEED_LIMIT = 1000.0


#----APPEND LOAD----
def _append_node_groups(names):
    """Append node groups as local copies and reuse resident local ones."""
    result = {}
    to_load = []
    for name in names:
        existing = bpy.data.node_groups.get(name)
        if existing is not None and existing.library is None:
            result[name] = existing
            continue
        if existing is not None:
            if existing.users == 0:
                bpy.data.node_groups.remove(existing)
            else:
                existing.name = f"{name}.linked_stale"
        to_load.append(name)
    if not to_load:
        return result
    with bpy.data.libraries.load(_NODE_GROUPS_BLEND, link=False) as (data_from, data_to):
        missing = [name for name in to_load if name not in data_from.node_groups]
        if missing:
            raise RuntimeError(f"Node group(s) {missing} not found in {_NODE_GROUPS_BLEND}")
        data_to.node_groups = to_load
    for node_group in data_to.node_groups:
        result[node_group.name] = node_group
    return result


def _append_node_group(name):
    """Append a single node group."""
    return _append_node_groups([name])[name]


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
        and modifier.node_group.name in EFFECTOR_NODE_GROUPS.values()
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
            and modifier.node_group.name == node_group_name
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


def get_modifier_input_path(modifier, socket_name):
    """RNA path of the modifier key backing a socket, or None."""
    if modifier is None or modifier.node_group is None:
        return None
    socket = find_input_socket(modifier.node_group, socket_name)
    if socket is None or socket.identifier not in modifier:
        return None
    return f'["{socket.identifier}"]'


def get_modifier_input_value(modifier, socket_name, fallback=None):
    """Read a socket value from the modifier, or fallback."""
    if modifier is None or modifier.node_group is None:
        return fallback
    socket = find_input_socket(modifier.node_group, socket_name)
    if socket is None:
        return fallback
    return modifier.get(socket.identifier, fallback)


def get_menu_socket_items(modifier, socket_name):
    """Return {item name: stored value} of a Menu socket; values are item ids, not positions."""
    if modifier is None or modifier.node_group is None:
        return {}
    socket = find_input_socket(modifier.node_group, socket_name)
    if socket is None or socket.identifier not in modifier:
        return {}
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
    if socket is None:
        return False
    try:
        modifier[socket.identifier] = value
    except TypeError:
        del modifier[socket.identifier]
        modifier[socket.identifier] = value
    modifier.id_data.update_tag()
    # visibility toggle forces the modifier to re-evaluate
    enabled = modifier.show_viewport
    modifier.show_viewport = not enabled
    modifier.show_viewport = enabled
    return True


def ensure_modifier_socket_defaults(modifier):
    """Materialize missing socket keys from node group defaults."""
    if modifier is None or modifier.node_group is None:
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
        modifier[socket.identifier] = target_ground
    elif socket.socket_type == 'NodeSocketString':
        uv_layers = target_ground.data.uv_layers
        if uv_layers.active is not None:
            modifier[socket.identifier] = uv_layers.active.name


def _wire_vertex_ground(modifier, target_ground):
    """Wire the vertex mask target ground socket."""
    if target_ground is None:
        return
    socket = find_input_socket(modifier.node_group, "Target Ground")
    if socket is not None:
        modifier[socket.identifier] = target_ground


def get_effector_node_group(effector_type):
    """Append and return the node group registered for an effector type."""
    group_name = EFFECTOR_NODE_GROUPS.get(effector_type)
    if group_name is None:
        return None
    return _append_node_group(group_name)


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
def _add_instances_modifier(curve_obj, group_name, pin_fake_user):
    """Create an instances modifier directly below the effector block."""
    node_group = _append_node_group(group_name)
    if pin_fake_user:
        node_group.use_fake_user = True
    modifier = curve_obj.modifiers.new(name=group_name, type='NODES')
    modifier.node_group = node_group
    ensure_modifier_socket_defaults(modifier)
    _move_modifier(curve_obj, modifier, _effector_block_end(curve_obj))
    return modifier


def _remove_instances_modifier(curve_obj, group_name):
    """Remove an instances modifier and keep its node group resident."""
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
    return _add_instances_modifier(curve_obj, INSTANCES_NODE_GROUP_NAME, pin_fake_user=False)


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
    return _add_instances_modifier(curve_obj, MANUAL_INSTANCES_NODE_GROUP_NAME, pin_fake_user=True)


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


#----SYSTEM SETUP----
def setup_system_modifier_stack(curve_obj, system_type, target_ground):
    """Create the points-stage modifier for a system and wire its target."""
    _deduplicate_surface_deform(curve_obj)
    if system_type == 'MANUAL':
        node_group = _append_node_group(MANUAL_POINTS_NODE_GROUP_NAME)
        modifier = curve_obj.modifiers.new(name=MANUAL_POINTS_NODE_GROUP_NAME, type='NODES')
        modifier.node_group = node_group
        ensure_modifier_socket_defaults(modifier)
        return modifier
    node_groups = _append_node_groups([PROCEDURAL_NODE_GROUP_NAME, INSTANCES_NODE_GROUP_NAME])
    node_group = node_groups[PROCEDURAL_NODE_GROUP_NAME]
    node_groups[INSTANCES_NODE_GROUP_NAME].use_fake_user = True
    modifier = curve_obj.modifiers.new(name=PROCEDURAL_NODE_GROUP_NAME, type='NODES')
    modifier.node_group = node_group
    ensure_modifier_socket_defaults(modifier)
    target_socket = _find_socket(node_group, "Target Ground")
    if target_socket is not None:
        modifier[target_socket.identifier] = target_ground
    return modifier


def duplicate_system_curve(curve_obj):
    """Copy a system's curve object (data + modifiers) into the same collections."""
    new_obj = curve_obj.copy()
    new_obj.data = curve_obj.data.copy()
    for collection in curve_obj.users_collection:
        collection.objects.link(new_obj)
    return new_obj


#----RESYNC----
def resync_node_groups_from_library():
    """Re-append library node groups and re-point existing modifiers."""
    names = [
        PROCEDURAL_NODE_GROUP_NAME, INSTANCES_NODE_GROUP_NAME, MANUAL_POINTS_NODE_GROUP_NAME,
    ]
    names += list(EFFECTOR_NODE_GROUPS.values())
    names.append(MANUAL_INSTANCES_NODE_GROUP_NAME)
    old = {}
    for name in names:
        existing = bpy.data.node_groups.get(name)
        if existing is not None:
            old[name] = existing
            existing.name = f"{name}.old"
    try:
        with bpy.data.libraries.load(_NODE_GROUPS_BLEND, link=False) as (data_from, data_to):
            missing = [name for name in names if name not in data_from.node_groups]
            if missing:
                raise RuntimeError(f"Node group(s) {missing} not found in {_NODE_GROUPS_BLEND}")
            data_to.node_groups = list(names)
    except Exception:
        for name, group in old.items():
            group.name = name
        raise
    fresh = dict(zip(names, data_to.node_groups))
    fresh[INSTANCES_NODE_GROUP_NAME].use_fake_user = True
    fresh[MANUAL_INSTANCES_NODE_GROUP_NAME].use_fake_user = True
    for obj in bpy.data.objects:
        for modifier in obj.modifiers:
            if modifier.type != 'NODES' or modifier.node_group is None:
                continue
            for base_name, old_group in old.items():
                if modifier.node_group == old_group:
                    modifier.node_group = fresh[base_name]
                    ensure_modifier_socket_defaults(modifier)
    for old_group in old.values():
        old_group.use_fake_user = False
        if old_group.users == 0:
            bpy.data.node_groups.remove(old_group)
    return True