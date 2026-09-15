from bpy.types import Operator
from bpy.props import EnumProperty

from ..properties import EFFECTOR_TYPE_ITEMS, EFFECTOR_TYPE_LABELS, EFFECTOR_TYPE_THUMBNAILS
from ..utils import icons as icon_utils


def _get_active_system(context):
    scene = context.scene
    g_idx = scene.active_ground_index
    if not (0 <= g_idx < len(scene.scatter_grounds)):
        return None
    ground = scene.scatter_grounds[g_idx]
    s_idx = ground.active_scatter_system_index
    if not (0 <= s_idx < len(ground.scatter_systems)):
        return None
    return ground.scatter_systems[s_idx]


def _tag_redraw_viewport(context):
    for area in context.screen.areas:
        if area.type == 'VIEW_3D':
            area.tag_redraw()


_effector_enum_cache = []


def _effector_enum_items(self, context):
    global _effector_enum_cache
    items = []
    for identifier, name, description, icon, index in EFFECTOR_TYPE_ITEMS:
        thumbnail_id = icon_utils.get_icon_id(EFFECTOR_TYPE_THUMBNAILS.get(identifier))
        items.append((identifier, name, description, thumbnail_id if thumbnail_id else icon, index))

    _effector_enum_cache = items
    return _effector_enum_cache


_EFFECTOR_DESCRIPTIONS = {identifier: description for identifier, _name, description, _icon, _idx in EFFECTOR_TYPE_ITEMS}


class SCATTER_OT_add_effector_popup(Operator):
    bl_idname = "scatter.add_effector_popup"
    bl_label = "Add Effector"
    bl_options = {'REGISTER', 'UNDO'}

    effector_type: EnumProperty(items=_effector_enum_items)

    @classmethod
    def poll(cls, context):
        return _get_active_system(context) is not None

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=360)

    def draw(self, context):
        layout = self.layout

        layout.template_icon_view(self, "effector_type", show_labels=True, scale=8.0)

        layout.separator(factor=0.5)
        footer = layout.column(align=True)
        footer.label(text=EFFECTOR_TYPE_LABELS.get(self.effector_type, ""), icon='INFO')
        info_row = footer.row()
        info_row.active = False
        info_row.label(text=_EFFECTOR_DESCRIPTIONS.get(self.effector_type, ""))

    def execute(self, context):
        system = _get_active_system(context)
        effector = system.effectors.add()
        effector.effector_type = self.effector_type
        effector.name = EFFECTOR_TYPE_LABELS.get(self.effector_type, "Effector")

        system.effectors.move(len(system.effectors) - 1, 0)
        system.active_effector_index = 0

        _tag_redraw_viewport(context)
        return {'FINISHED'}


class SCATTER_OT_remove_effector(Operator):
    bl_idname = "scatter.remove_effector"
    bl_label = "Remove effector"

    @classmethod
    def poll(cls, context):
        system = _get_active_system(context)
        if system is None:
            return False
        return 0 <= system.active_effector_index < len(system.effectors)

    def execute(self, context):
        system = _get_active_system(context)
        system.effectors.remove(system.active_effector_index)
        system.active_effector_index = max(0, system.active_effector_index - 1)

        _tag_redraw_viewport(context)
        return {'FINISHED'}


class SCATTER_OT_move_effector(Operator):
    bl_idname = "scatter.move_effector"
    bl_label = "Move effector"

    direction: EnumProperty(
        items=[('UP', "Up", ""), ('DOWN', "Down", "")],
        default='UP',
    )

    @classmethod
    def poll(cls, context):
        system = _get_active_system(context)
        if system is None:
            return False
        return 0 <= system.active_effector_index < len(system.effectors)

    def execute(self, context):
        system = _get_active_system(context)
        idx = system.active_effector_index
        new_idx = idx - 1 if self.direction == 'UP' else idx + 1

        if not (0 <= new_idx < len(system.effectors)):
            return {'CANCELLED'}

        system.effectors.move(idx, new_idx)
        system.active_effector_index = new_idx

        _tag_redraw_viewport(context)
        return {'FINISHED'}


classes = (
    SCATTER_OT_add_effector_popup,
    SCATTER_OT_remove_effector,
    SCATTER_OT_move_effector,
)