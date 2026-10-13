"""Popup and pie menus for the scatter panel."""
import bpy
from bpy.types import Menu

from ..operators.system_ops import SYSTEM_TYPE_ITEMS
from ..properties import (
    BRUSH_ICON_NAMES, BRUSH_TYPE_ITEMS,
    EFFECTOR_ICON_NAMES, EFFECTOR_TYPE_ITEMS, PROCEDURAL_ONLY_EFFECTORS,
)
from ..utils import geonodes as geonodes_utils
from ..utils import icons as icon_utils


_BRUSH_PIE_ORDER = ('LINE', 'DENSITY', 'DELETE', 'GROW', 'SLIDE')
_BRUSH_ITEMS_BY_ID = {item[0]: item for item in BRUSH_TYPE_ITEMS}


def _get_active_system(context):
    scene = context.scene
    ground_idx = scene.active_ground_index
    if not (0 <= ground_idx < len(scene.scatter_grounds)):
        return None
    ground = scene.scatter_grounds[ground_idx]
    system_idx = ground.active_scatter_system_index
    if not (0 <= system_idx < len(ground.scatter_systems)):
        return None
    return ground.scatter_systems[system_idx]


class SCATTER_MT_grounds(Menu):
    bl_idname = "SCATTER_MT_grounds"
    bl_label = "Grounds"

    def draw(self, context):
        layout = self.layout
        active_idx = context.scene.active_ground_index
        for index, ground in enumerate(context.scene.scatter_grounds):
            icon = 'RADIOBUT_ON' if index == active_idx else 'RADIOBUT_OFF'
            op = layout.operator("scatter.set_active_ground", text=ground.name, icon=icon)
            op.index = index


class SCATTER_MT_add_system_type(Menu):
    bl_idname = "SCATTER_MT_add_system_type"
    bl_label = "Add Scatter System"
    bl_ui_units_x = 20

    def draw(self, context):
        layout = self.layout
        for identifier, name, _description, builtin_icon, _index in SYSTEM_TYPE_ITEMS:
            menu_icon = icon_utils.get_menu_icon_id(identifier.lower())
            if menu_icon:
                op = layout.operator("scatter.add_system", text=name, icon_value=menu_icon)
            else:
                op = layout.operator("scatter.add_system", text=name, icon=builtin_icon)
            op.system_type = identifier


class SCATTER_MT_add_effector(Menu):
    bl_idname = "SCATTER_MT_add_effector"
    bl_label = "Add Mask"
    bl_ui_units_x = 20

    def draw(self, context):
        layout = self.layout
        system = _get_active_system(context)
        is_manual = system is not None and system.system_type == 'MANUAL'
        for identifier, name, _description, builtin_icon, _index in EFFECTOR_TYPE_ITEMS:
            if identifier not in geonodes_utils.EFFECTOR_NODE_GROUPS:
                continue
            if is_manual and identifier in PROCEDURAL_ONLY_EFFECTORS:
                continue
            menu_icon = icon_utils.get_menu_icon_id(EFFECTOR_ICON_NAMES.get(identifier))
            if menu_icon:
                op = layout.operator("scatter.add_effector", text=name, icon_value=menu_icon)
            else:
                op = layout.operator("scatter.add_effector", text=name, icon=builtin_icon)
            op.effector_type = identifier


class SCATTER_MT_brush_pie(Menu):
    bl_idname = "SCATTER_MT_brush_pie"
    bl_label = "Scatter Brush"

    @classmethod
    def poll(cls, context):
        return bpy.ops.scatter.stop_manual_paint.poll()

    def draw(self, context):
        active = context.scene.scatter_active_brush
        pie = self.layout.menu_pie()
        for identifier in _BRUSH_PIE_ORDER:
            _id, name, _description, builtin_icon, _index = _BRUSH_ITEMS_BY_ID[identifier]
            label = f"●  {name}" if identifier == active else name
            thumbnail = icon_utils.get_menu_icon_id(BRUSH_ICON_NAMES.get(identifier))
            if thumbnail:
                props = pie.operator("scatter.set_brush", text=label, icon_value=thumbnail)
            else:
                props = pie.operator("scatter.set_brush", text=label, icon=builtin_icon)
            props.brush = identifier
        pie.operator("scatter.stop_manual_paint", text="Exit", icon='X')


classes = (
    SCATTER_MT_grounds,
    SCATTER_MT_add_system_type,
    SCATTER_MT_add_effector,
    SCATTER_MT_brush_pie,
)