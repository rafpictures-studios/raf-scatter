"""
utils/geonodes.py — Helper functions for reading/setting up Geometry
Nodes.

Node groups are linked (not appended) from resources/node_groups.blend,
per Rule H. Socket identifiers are always resolved by name at runtime
via node_tree.interface.items_tree — never hardcoded.
"""

import os
import bpy

_NODE_GROUPS_BLEND = os.path.join(
    os.path.dirname(__file__), "..", "resources", "node_groups.blend"
)

PROCEDURAL_NODE_GROUP_NAME = "gn_proceduralScatter_points"
INSTANCES_NODE_GROUP_NAME = "gn_proceduralScatter_instances"
SURFACE_DEFORM_NAME_PREFIX = "Surface Deform"


def _link_node_groups(names):
    """Link one or more node groups from resources/node_groups.blend in
    a single library load. Returns a dict of name -> node_group. Names
    already resident in bpy.data.node_groups (linked earlier this
    session) are returned as-is without touching the library file."""
    result = {}
    to_load = []
    for name in names:
        existing = bpy.data.node_groups.get(name)
        if existing is not None:
            result[name] = existing
        else:
            to_load.append(name)

    if not to_load:
        return result

    with bpy.data.libraries.load(_NODE_GROUPS_BLEND, link=True) as (data_from, data_to):
        missing = [name for name in to_load if name not in data_from.node_groups]
        if missing:
            raise RuntimeError(f"Node group(s) {missing} not found in {_NODE_GROUPS_BLEND}")
        data_to.node_groups = to_load

    # Blender mutates data_to.node_groups in place after the `with`
    # block exits, replacing the name strings with the actual loaded
    # datablocks. Since data_to.node_groups and to_load are the same
    # list object, to_load itself is no longer a list of strings here
    # -- iterate the loaded datablocks directly, never bpy.data
    # .node_groups.get() on the original name strings past this point.
    for node_group in data_to.node_groups:
        result[node_group.name] = node_group

    return result


def _link_node_group(name):
    """Link a single node group. Thin wrapper over _link_node_groups()."""
    return _link_node_groups([name])[name]


def reload_node_groups_library():
    """PENDING VERIFICATION: force-reload the linked library so
    in-scene modifiers pick up interface edits (new sockets, changed
    subtypes) made directly in resources/node_groups.blend, without
    needing to delete/recreate existing Scatter Systems. Call from
    the Python console after editing that file. Relies on the linked
    library being registered under its filename in bpy.data.libraries
    — not yet confirmed against a live Blender session."""
    library = bpy.data.libraries.get(os.path.basename(_NODE_GROUPS_BLEND))
    if library is None:
        return False

    library.reload()
    return True


def _find_socket(node_tree, socket_name):
    for item in node_tree.interface.items_tree:
        if item.item_type == 'SOCKET' and item.name == socket_name:
            return item
    return None


def find_input_socket(node_tree, socket_name):
    for item in node_tree.interface.items_tree:
        if (
            item.item_type == 'SOCKET'
            and item.in_out == 'INPUT'
            and item.name == socket_name
        ):
            return item
    return None


def find_modifier_by_node_group(curve_obj, node_group_name):
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
    if system is None or system.system_type != 'PROCEDURAL':
        return None
    return find_modifier_by_node_group(system.curve_obj, PROCEDURAL_NODE_GROUP_NAME)


def get_instances_modifier(system):
    if system is None or system.system_type != 'PROCEDURAL':
        return None
    return find_modifier_by_node_group(system.curve_obj, INSTANCES_NODE_GROUP_NAME)


def get_modifier_input_path(modifier, socket_name):
    if modifier is None or modifier.node_group is None:
        return None

    socket = find_input_socket(modifier.node_group, socket_name)
    if socket is None or socket.identifier not in modifier:
        return None

    return f'["{socket.identifier}"]'


def get_modifier_input_value(modifier, socket_name, fallback=None):
    if modifier is None or modifier.node_group is None:
        return fallback

    socket = find_input_socket(modifier.node_group, socket_name)
    if socket is None:
        return fallback

    return modifier.get(socket.identifier, fallback)


def set_modifier_input_value(modifier, socket_name, value):
    if modifier is None or modifier.node_group is None:
        return False

    socket = find_input_socket(modifier.node_group, socket_name)
    if socket is None:
        return False

    modifier[socket.identifier] = value
    return True


def _deduplicate_surface_deform(curve_obj):
    """curves_empty_hair_add() auto-adds a Surface Deform modifier
    bound to the active surface. Repeated Add System calls (or
    undo/redo edge cases) can leave more than one such modifier, or a
    second node-group datablock suffixed '.001'. Collapse to one so
    the modifier stack never shows a duplicate."""
    base_group = bpy.data.node_groups.get(SURFACE_DEFORM_NAME_PREFIX)

    surface_deform_mods = [
        mod for mod in curve_obj.modifiers
        if (mod.type == 'SURFACE_DEFORM')
        or (mod.type == 'NODES' and mod.node_group and mod.node_group.name.startswith(SURFACE_DEFORM_NAME_PREFIX))
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


def get_effector_node_group(effector_type):
    """TODO: Effector node groups aren't authored in
    resources/node_groups.blend yet — only gn_proceduralScatter_points
    and gn_proceduralScatter_instances exist so far (Section 7)."""
    raise NotImplementedError


def read_node_group_inputs(node_group):
    """Return input sockets as dicts (name, identifier, socket_type,
    default_value, min_value, max_value) for generating dynamic
    sliders in ui/panels.py (Section 9, roadmap item 2)."""
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


def append_effector_to_stack(curve_obj, effector_type):
    """TODO: depends on get_effector_node_group() — Effector node
    groups not authored yet."""
    raise NotImplementedError


def add_instances_modifier(curve_obj):
    """Create the gn_proceduralScatter_instances modifier on curve_obj,
    appended at the end of the stack (after the Points modifier).
    Assumes Points is currently the last modifier when this is called
    — true for the stack as it exists today (Surface Deform, then
    Points), but flag it if a future modifier ever gets inserted after
    Points and before this is called, since modifiers.new() always
    appends at the end."""
    node_group = _link_node_group(INSTANCES_NODE_GROUP_NAME)

    modifier = curve_obj.modifiers.new(name=INSTANCES_NODE_GROUP_NAME, type='NODES')
    modifier.node_group = node_group
    return modifier


def remove_instances_modifier(curve_obj):
    """Remove the gn_proceduralScatter_instances modifier if present.
    Deliberately does NOT unlink/remove the node_group datablock —
    it stays resident in bpy.data so toggling back on is instant."""
    modifier = find_modifier_by_node_group(curve_obj, INSTANCES_NODE_GROUP_NAME)
    if modifier is None:
        return False

    curve_obj.modifiers.remove(modifier)
    return True


def setup_system_modifier_stack(curve_obj, system_type, target_ground):
    """Set up the initial GeoNodes modifier on curve_obj for the given
    system_type. Currently only PROCEDURAL gets its own modifier
    (Section 7); MANUAL systems only get the dedup pass below. Wires
    Target Ground by socket name (Rule H) and leaves it undrawn in
    the N-panel.

    For PROCEDURAL systems, gn_proceduralScatter_instances is linked
    here too (but not turned into a modifier yet) so the later
    'Use Instances' toggle (procedural_ops.py) only has to create or
    remove a modifier, not touch the library file — keeps that button
    fast."""
    _deduplicate_surface_deform(curve_obj)

    if system_type != 'PROCEDURAL':
        return None

    node_groups = _link_node_groups([PROCEDURAL_NODE_GROUP_NAME, INSTANCES_NODE_GROUP_NAME])
    node_group = node_groups[PROCEDURAL_NODE_GROUP_NAME]

    modifier = curve_obj.modifiers.new(name=PROCEDURAL_NODE_GROUP_NAME, type='NODES')
    modifier.node_group = node_group

    target_socket = _find_socket(node_group, "Target Ground")
    if target_socket is not None:
        modifier[target_socket.identifier] = target_ground

    return modifier