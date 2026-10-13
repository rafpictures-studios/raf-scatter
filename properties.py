"""PropertyGroups, Scene properties, update callbacks and rename sync."""
import re

import bpy
from bpy.props import (
    BoolProperty, CollectionProperty, EnumProperty,
    IntProperty, PointerProperty, StringProperty,
)
from bpy.types import PropertyGroup

from .utils import brushes as brush_utils, geonodes as geonodes_utils, icons as icon_utils


#----TYPE CONSTANTS----
EFFECTOR_TYPE_ITEMS = (
    ('MASK_BY_TEXTURE', "Texture Mask", "Noise, voronoi, wave and more", 'TEXTURE', 0),
    ('MASK_BY_POSITION', "Position Mask", "Based on point position", 'EMPTY_AXIS', 1),
    ('MASK_BY_NORMAL', "Slope Mask", "Based on surface normal", 'NORMALS_FACE', 2),
    ('GEOMETRY_PROXIMITY', "Proximity Mask", "By object or by collection", 'CON_DISTLIMIT', 3),
    ('MASK_BY_ATTRIBUTE', "Vertex Mask", "Weight paint or color attribute", 'GROUP_VCOL', 4),
)
EFFECTOR_TYPE_ICONS = {identifier: icon for identifier, _, _, icon, _ in EFFECTOR_TYPE_ITEMS}
EFFECTOR_TYPE_LABELS = {identifier: name for identifier, name, _, _, _ in EFFECTOR_TYPE_ITEMS}
EFFECTOR_ICON_NAMES = {
    'MASK_BY_TEXTURE': "texture_mask",
    'MASK_BY_POSITION': "position_mask",
    'MASK_BY_NORMAL': "slope_mask",
    'GEOMETRY_PROXIMITY': "proximity_mask",
    'MASK_BY_ATTRIBUTE': "vertex_mask",
}
PROCEDURAL_ONLY_EFFECTORS = {'MASK_BY_NORMAL', 'MASK_BY_ATTRIBUTE'}
SYSTEM_AUTO_NAME_SUFFIX = "_scatter"
_AUTO_SYSTEM_NAME_RE = re.compile(
    r"^(?:(?:paintScatter|manualScatter|proceduralScatter)_\d{2,}|.+" + SYSTEM_AUTO_NAME_SUFFIX + r")(?:\.\d{3})?$"
)
_NAME_NUMBER_SUFFIX_RE = re.compile(r"\.\d{3}$")
VERTEX_MASK_GROUP_PREFIX = "wp_scatter"
BRUSH_TYPE_ITEMS = (
    ('LINE', "Add", "Add — place new points on the target surface", 'ADD', 0),
    (
        'DENSITY', "Density", "Density — increase or decrease point density locally",
        'STICKY_UVS_LOC', 1,
    ),
    ('GROW', "Grow", "Grow — grow points within the brush area", 'ZOOM_IN', 2),
    ('DELETE', "Delete", "Delete — remove points within the brush area", 'TRASH', 3),
    ('SLIDE', "Slide", "Slide — slide points along the target surface", 'ARROW_LEFTRIGHT', 4),
)
BRUSH_ICON_NAMES = {
    'LINE': "brush_line",
    'DENSITY': "brush_density",
    'GROW': "brush_grow",
    'DELETE': "brush_delete",
    'SLIDE': "brush_slide",
}


#----MODULE STATE----
_brush_enum_cache = []


#----PICKER POLLS----
def _object_in_scene(scene, obj):
    """Return True when the object exists in the scene by name."""
    return obj.name in scene.objects


def _is_registered_ground(scene, obj):
    """Return True when the object is already a target ground."""
    for ground in scene.scatter_grounds:
        if ground.target_object == obj:
            return True
    return False


def _mesh_only_poll(self, obj):
    """Ground picker poll: mesh, in scene, and not already a ground."""
    if obj.type != 'MESH':
        return False
    if not _object_in_scene(self, obj):
        return False
    return not _is_registered_ground(self, obj)


def _mesh_in_scene_poll(self, obj):
    """Shared picker poll: mesh, in scene, and never a target ground."""
    if obj is None:
        return True
    if obj.type != 'MESH':
        return False
    scene = bpy.context.scene
    if not _object_in_scene(scene, obj):
        return False
    return not _is_registered_ground(scene, obj)


_proximity_object_poll = _mesh_in_scene_poll
_instances_object_poll = _mesh_in_scene_poll


def is_pickable_mesh(obj):
    """Return True when an object passes the shared mesh picker poll."""
    return obj is not None and _mesh_in_scene_poll(None, obj)


#----BRUSH CALLBACKS----
def _brush_type_enum_items(self, context):
    """Return brush enum items with thumbnail icons."""
    global _brush_enum_cache
    items = []
    for identifier, name, description, icon, index in BRUSH_TYPE_ITEMS:
        thumbnail_id = icon_utils.get_menu_icon_id(BRUSH_ICON_NAMES.get(identifier))
        items.append((
            identifier, name, description,
            thumbnail_id if thumbnail_id else icon, index,
        ))
    _brush_enum_cache = items
    return _brush_enum_cache


def _paint_session_active(scene):
    """Return True while a paint session runs on a curve that is in sculpt mode."""
    if not scene.scatter_paint_ui_saved:
        return False
    curve_obj = scene.scatter_paint_curve_obj
    return curve_obj is not None and curve_obj.mode == 'SCULPT_CURVES'


def _on_active_brush_update(self, context):
    """Activate the matching native brush and select all curve points during a session."""
    if not _paint_session_active(self):
        return
    brush_utils.apply_active_brush(self)
    brush_utils.activate_scatter_tool(self.scatter_active_brush)
    brush_utils.select_all_curve_points(context)


#----EFFECTOR CALLBACKS----
def _effector_modifier(item):
    """Return the modifier mirrored by an effector item."""
    if item.curve_obj is None or not item.modifier_name:
        return None
    return item.curve_obj.modifiers.get(item.modifier_name)


def _on_effector_name_update(self, context):
    """Push the effector rename onto its modifier and reflect suffixes."""
    modifier = _effector_modifier(self)
    if modifier is None or modifier.name == self.name:
        return
    modifier.name = self.name
    self.modifier_name = modifier.name
    if modifier.name != self.name:
        self.name = modifier.name


def _on_vertex_group_name_update(self, context):
    """Mirror the vertex group name onto the effector Attribute socket."""
    modifier = _effector_modifier(self)
    if modifier is not None:
        geonodes_utils.set_modifier_input_value(modifier, "Attribute", self.vertex_group_name)


def _on_proximity_object_update(self, context):
    """Mirror the proximity object picker onto the modifier."""
    modifier = _effector_modifier(self)
    if modifier is not None:
        geonodes_utils.set_modifier_input_value(modifier, "Object", self.proximity_object)


def _on_proximity_collection_update(self, context):
    """Mirror the proximity collection picker onto the modifier."""
    modifier = _effector_modifier(self)
    if modifier is not None:
        geonodes_utils.set_modifier_input_value(modifier, "Collection", self.proximity_collection)


#----SYSTEM AUTO NAME----
def _is_auto_system_name(name):
    """Return True for names the addon generated, which may be replaced automatically."""
    return bool(_AUTO_SYSTEM_NAME_RE.match(name))


def sync_system_auto_name(system):
    """Rename an auto-named system after its active instance source, plus the suffix."""
    if system.system_type == 'MANUAL':
        mode = system.manual_instances_mode
        source = system.manual_instances_collection if mode == 1 else system.manual_instances_object
    else:
        mode = system.instances_mode
        source = system.instances_collection if mode == 1 else system.instances_object
    if source is None or not _is_auto_system_name(system.name):
        return
    new_name = source.name + SYSTEM_AUTO_NAME_SUFFIX
    if _NAME_NUMBER_SUFFIX_RE.sub("", system.name) != new_name:
        system.name = new_name


def _on_active_effector_index_update(self, context):
    """A plain pick of the active effector selects only that effector, like the Outliner."""
    for index, effector in enumerate(self.effectors):
        effector.selected = index == self.active_effector_index


#----SYSTEM CALLBACKS----
def _on_instances_object_update(self, context):
    """Mirror the procedural object picker onto the instances modifier."""
    modifier = geonodes_utils.get_instances_modifier(self)
    if modifier is not None:
        geonodes_utils.set_modifier_input_value(modifier, "Object", self.instances_object)
    sync_system_auto_name(self)


def _on_instances_collection_update(self, context):
    """Mirror the procedural collection picker onto the instances modifier."""
    modifier = geonodes_utils.get_instances_modifier(self)
    if modifier is not None:
        geonodes_utils.set_modifier_input_value(modifier, "Collection", self.instances_collection)
    sync_system_auto_name(self)


def _on_manual_instances_object_update(self, context):
    """Mirror the manual object picker onto the manual instances modifier."""
    modifier = geonodes_utils.get_manual_instances_modifier(self)
    if modifier is not None:
        geonodes_utils.set_modifier_input_value(modifier, "Object", self.manual_instances_object)
    sync_system_auto_name(self)


def _on_manual_instances_collection_update(self, context):
    """Mirror the manual collection picker onto the manual instances modifier."""
    modifier = geonodes_utils.get_manual_instances_modifier(self)
    if modifier is not None:
        geonodes_utils.set_modifier_input_value(
            modifier, "Collection", self.manual_instances_collection,
        )
    sync_system_auto_name(self)


def _on_system_name_update(self, context):
    """Push the system rename onto the curve object and reflect suffixes."""
    if self.curve_obj is None:
        return
    if self.curve_obj.name == self.name:
        return
    self.curve_obj.name = self.name
    if self.curve_obj.name != self.name:
        self.name = self.curve_obj.name


def _sync_curve_renames(scene, depsgraph):
    """Sync outside curve renames and heal modifier socket keys."""
    for ground in scene.scatter_grounds:
        for system in ground.scatter_systems:
            if system.curve_obj is not None and system.curve_obj.name != system.name:
                system.name = system.curve_obj.name
            geonodes_utils.resync_effector_modifier_links(system)
            geonodes_utils.ensure_system_modifier_defaults(system)


#----GROUND CALLBACKS----
def _on_active_system_index_update(self, context):
    """Select the active system curve and leave sculpt mode when needed."""
    idx = self.active_scatter_system_index
    if not (0 <= idx < len(self.scatter_systems)):
        return
    system = self.scatter_systems[idx]
    if system.curve_obj is None:
        return
    scene = context.scene
    painting = scene.scatter_paint_curve_obj
    if (
        getattr(scene, "scatter_paint_ui_saved", False)
        and painting is not None
        and painting.name != system.curve_obj.name
        and painting.mode == 'SCULPT_CURVES'
    ):
        try:
            bpy.ops.object.mode_set(mode='OBJECT')
        except RuntimeError:
            pass
        scene.scatter_paint_ui_saved = False
        scene.scatter_paint_curve_obj = None
    for obj in context.selected_objects:
        obj.select_set(False)
    system.curve_obj.select_set(True)
    context.view_layer.objects.active = system.curve_obj


#----PROPERTY GROUPS----
class SCATTER_EffectorItem(PropertyGroup):
    name: StringProperty(name="Mask name", default="Mask", update=_on_effector_name_update)
    effector_type: EnumProperty(name="Type", items=EFFECTOR_TYPE_ITEMS, default='MASK_BY_TEXTURE')
    modifier_name: StringProperty(name="Modifier name", default="")
    curve_obj: PointerProperty(name="Curve object", type=bpy.types.Object)
    selected: BoolProperty(name="Selected", default=False)
    vertex_mode: IntProperty(name="Vertex mask mode", default=0, min=0, max=1)
    vertex_group_name: StringProperty(
        name="Vertex Group", default="", update=_on_vertex_group_name_update,
    )
    proximity_object: PointerProperty(
        name="Object", type=bpy.types.Object,
        poll=_proximity_object_poll, update=_on_proximity_object_update,
    )
    proximity_collection: PointerProperty(
        name="Collection", type=bpy.types.Collection,
        update=_on_proximity_collection_update,
    )


class SCATTER_SystemItem(PropertyGroup):
    name: StringProperty(name="System name", default="ScatterSystem", update=_on_system_name_update)
    system_type: EnumProperty(
        name="Type",
        items=[
            ('MANUAL', "Paint", "Points painted by hand via curve sculpting"),
            ('PROCEDURAL', "Procedural", "Points generated automatically (distribute on faces)"),
        ],
        default='MANUAL',
    )
    target_ground: PointerProperty(name="Target ground", type=bpy.types.Object)
    curve_obj: PointerProperty(name="Curve object", type=bpy.types.Object)
    instances_object: PointerProperty(
        name="Object", type=bpy.types.Object,
        poll=_instances_object_poll, update=_on_instances_object_update,
    )
    instances_collection: PointerProperty(
        name="Collection", type=bpy.types.Collection,
        update=_on_instances_collection_update,
    )
    instances_mode: IntProperty(name="Instances mode", default=0, min=0, max=1)
    manual_instances_object: PointerProperty(
        name="Object", type=bpy.types.Object,
        poll=_instances_object_poll, update=_on_manual_instances_object_update,
    )
    manual_instances_collection: PointerProperty(
        name="Collection", type=bpy.types.Collection,
        update=_on_manual_instances_collection_update,
    )
    manual_instances_mode: IntProperty(name="Instances mode", default=0, min=0, max=1)
    effectors: CollectionProperty(type=SCATTER_EffectorItem)
    active_effector_index: IntProperty(default=0, update=_on_active_effector_index_update)


class SCATTER_GroundItem(PropertyGroup):
    """One target ground with its own independent scatter system stack."""
    name: StringProperty(name="Ground name", default="Ground")
    target_object: PointerProperty(name="Target object", type=bpy.types.Object)
    scatter_systems: CollectionProperty(type=SCATTER_SystemItem)
    active_scatter_system_index: IntProperty(default=0, update=_on_active_system_index_update)


#----REGISTRATION----
classes = (
    SCATTER_EffectorItem,
    SCATTER_SystemItem,
    SCATTER_GroundItem,
)


def register():
    """Register property classes and scene properties."""
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.scatter_grounds = CollectionProperty(type=SCATTER_GroundItem)
    bpy.types.Scene.active_ground_index = IntProperty(default=0)
    bpy.types.Scene.scatter_ground_picker_temp = PointerProperty(
        name="Target Ground", type=bpy.types.Object, poll=_mesh_only_poll,
    )
    bpy.types.Scene.scatter_effector_search = StringProperty(name="Search", default="")
    bpy.types.Scene.scatter_active_brush = EnumProperty(
        name="Brush", items=_brush_type_enum_items, update=_on_active_brush_update,
    )
    bpy.types.Scene.scatter_effector_clipboard = StringProperty(
        name="Mask clipboard", default="", options={'HIDDEN'},
    )
    bpy.types.Scene.scatter_paint_ui_saved = BoolProperty(default=False)
    bpy.types.Scene.scatter_paint_curve_obj = PointerProperty(
        name="Painting curve object", type=bpy.types.Object,
    )
    bpy.app.handlers.depsgraph_update_post.append(_sync_curve_renames)


def unregister():
    """Unregister property classes and remove scene properties."""
    if _sync_curve_renames in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_sync_curve_renames)
    del bpy.types.Scene.scatter_paint_curve_obj
    del bpy.types.Scene.scatter_paint_ui_saved
    del bpy.types.Scene.scatter_effector_clipboard
    del bpy.types.Scene.scatter_active_brush
    del bpy.types.Scene.scatter_effector_search
    del bpy.types.Scene.scatter_ground_picker_temp
    del bpy.types.Scene.active_ground_index
    del bpy.types.Scene.scatter_grounds
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)