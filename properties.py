import bpy
from bpy.props import (
    StringProperty, BoolProperty, FloatProperty, EnumProperty,
    PointerProperty, CollectionProperty, IntProperty,
)
from bpy.types import PropertyGroup

from .utils import icons as icon_utils


def _mesh_only_poll(self, obj):
    """Rule F: mesh-only, and excludes objects already used as a
    Target Ground elsewhere (one object -> one ground, no duplicates).
    self is the Scene here (property owner)."""
    if obj.type != 'MESH':
        return False
    for ground in self.scatter_grounds:
        if ground.target_object == obj:
            return False
    return True


EFFECTOR_TYPE_ITEMS = (
    ('MASK_BY_TEXTURE', "Texture Mask", "Noise, voronoi, wave and more", 'TEXTURE', 0),
    ('GEOMETRY_PROXIMITY', "Proximity Mask", "By object or by collection", 'CON_DISTLIMIT', 1),
    ('MASK_BY_POSITION', "Position Mask", "Based on point position", 'EMPTY_AXIS', 2),
    ('MASK_BY_NORMAL', "Slope Mask", "Based on surface normal", 'NORMALS_FACE', 3),
    ('MASK_BY_ATTRIBUTE', "Vertex Mask", "Weight paint or color attribute", 'GROUP_VCOL', 4),
)

EFFECTOR_TYPE_ICONS = {identifier: icon for identifier, _, _, icon, _ in EFFECTOR_TYPE_ITEMS}
EFFECTOR_TYPE_LABELS = {identifier: name for identifier, name, _, _, _ in EFFECTOR_TYPE_ITEMS}

EFFECTOR_TYPE_THUMBNAILS = {
    'MASK_BY_TEXTURE': "texture_mask",
    'GEOMETRY_PROXIMITY': "proximity_mask",
    'MASK_BY_POSITION': "position_mask",
    'MASK_BY_NORMAL': "slope_mask",
    'MASK_BY_ATTRIBUTE': "vertex_mask",
}


BRUSH_TYPE_ITEMS = (
    ('LINE', "Line", "Line — place new points on the target surface", 'ADD', 0),
    ('DENSITY', "Density", "Density — increase or decrease point density locally", 'STICKY_UVS_LOC', 1),
    ('DELETE', "Delete", "Delete — remove points within the brush area", 'TRASH', 2),
    ('SLIDE', "Slide", "Slide — slide points along the target surface", 'ARROW_LEFTRIGHT', 3),
)

BRUSH_TYPE_THUMBNAILS = {
    'LINE': "brush_line",
    'DENSITY': "brush_density",
    'DELETE': "brush_delete",
    'SLIDE': "brush_slide",
}

_brush_enum_cache = []


def _brush_type_enum_items(self, context):
    global _brush_enum_cache
    items = []
    for identifier, name, description, icon, index in BRUSH_TYPE_ITEMS:
        thumbnail_id = icon_utils.get_icon_id(BRUSH_TYPE_THUMBNAILS.get(identifier))
        items.append((identifier, name, description, thumbnail_id if thumbnail_id else icon, index))

    _brush_enum_cache = items
    return _brush_enum_cache


class SCATTER_EffectorItem(PropertyGroup):
    name: StringProperty(name="Effector name", default="Effector")
    effector_type: EnumProperty(name="Type", items=EFFECTOR_TYPE_ITEMS, default='MASK_BY_TEXTURE')

    density: FloatProperty(name="Density", default=0.5, min=0.0, max=1.0)
    scale_variance: FloatProperty(name="Scale variance", default=0.3, min=0.0, max=1.0)


def _on_active_system_index_update(self, context):
    """Rule G: selecting a Scatter System in the list mirrors the
    selection onto its curve_obj in the viewport/Outliner. self here
    is the owning SCATTER_GroundItem."""
    idx = self.active_scatter_system_index
    if not (0 <= idx < len(self.scatter_systems)):
        return

    system = self.scatter_systems[idx]
    if system.curve_obj is None:
        return

    for obj in context.selected_objects:
        obj.select_set(False)

    system.curve_obj.select_set(True)
    context.view_layer.objects.active = system.curve_obj


def _on_system_name_update(self, context):
    """Two-way rename sync (author request): renaming the system item
    in the addon's list pushes the new name onto its curve_obj. self
    is the SCATTER_SystemItem being renamed. If Blender auto-suffixes
    the object name for global uniqueness, the actual resulting name
    is reflected back onto the item so the two never diverge.
    See utils via _sync_curve_renames() for the reverse direction
    (renaming the object itself, e.g. via the Outliner)."""
    if self.curve_obj is None:
        return
    if self.curve_obj.name == self.name:
        return
    self.curve_obj.name = self.name
    if self.curve_obj.name != self.name:
        self.name = self.curve_obj.name


def _sync_curve_renames(scene, depsgraph):
    """PENDING VERIFICATION: reverse direction of _on_system_name_update
    — if a curve_obj was renamed directly (e.g. via the Outliner)
    rather than through the addon's list, reflect that back onto its
    Scatter System item's name. Runs on depsgraph_update_post; cheap
    given the addon's expected small object counts, but not yet
    tested against real Outliner rename / undo-redo behavior."""
    for ground in scene.scatter_grounds:
        for system in ground.scatter_systems:
            if system.curve_obj is not None and system.curve_obj.name != system.name:
                system.name = system.curve_obj.name


class SCATTER_SystemItem(PropertyGroup):
    name: StringProperty(name="System name", default="ScatterSystem", update=_on_system_name_update)

    system_type: EnumProperty(
        name="Type",
        items=[
            ('MANUAL', "Manual", "Points placed manually via curve sculpting"),
            ('PROCEDURAL', "Procedural", "Points generated automatically (distribute on faces)"),
        ],
        default='MANUAL',
    )

    target_ground: PointerProperty(name="Target ground", type=bpy.types.Object)
    curve_obj: PointerProperty(name="Curve object", type=bpy.types.Object)

    effectors: CollectionProperty(type=SCATTER_EffectorItem)
    active_effector_index: IntProperty(default=0)


class SCATTER_GroundItem(PropertyGroup):
    """One target ground, with its own independent scatter system stack."""
    name: StringProperty(name="Ground name", default="Ground")

    target_object: PointerProperty(name="Target object", type=bpy.types.Object)

    scatter_systems: CollectionProperty(type=SCATTER_SystemItem)
    active_scatter_system_index: IntProperty(default=0, update=_on_active_system_index_update)


classes = (
    SCATTER_EffectorItem,
    SCATTER_SystemItem,
    SCATTER_GroundItem,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.scatter_grounds = CollectionProperty(type=SCATTER_GroundItem)
    bpy.types.Scene.active_ground_index = IntProperty(default=0)
    bpy.types.Scene.scatter_ground_picker_temp = PointerProperty(
        name="Target Ground",
        type=bpy.types.Object,
        poll=_mesh_only_poll,
    )
    bpy.types.Scene.scatter_effector_search = StringProperty(name="Search", default="")

    bpy.types.Scene.scatter_manual_mode_on = BoolProperty(default=False)
    bpy.types.Scene.scatter_active_brush = EnumProperty(
        name="Brush",
        items=_brush_type_enum_items,
    )

    bpy.app.handlers.depsgraph_update_post.append(_sync_curve_renames)


def unregister():
    if _sync_curve_renames in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_sync_curve_renames)

    del bpy.types.Scene.scatter_active_brush
    del bpy.types.Scene.scatter_manual_mode_on
    del bpy.types.Scene.scatter_effector_search
    del bpy.types.Scene.scatter_ground_picker_temp
    del bpy.types.Scene.active_ground_index
    del bpy.types.Scene.scatter_grounds

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)