"""Operators for animated instances (wind)."""
import json

from bpy.types import Operator

from ..utils import geonodes as geonodes_utils


#----ACTIVE LOOKUP----
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


#----OPERATORS----
class SCATTER_OT_toggle_wind(Operator):
    bl_idname = "scatter.toggle_wind"
    bl_label = "Wind"
    bl_description = (
        "Animate the instances with wind. While it is on, Random Rotation is 0 and Align Surface "
        "is off; turning it off gives them their values back"
    )
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        system = _get_active_system(context)
        return geonodes_utils.get_system_instances_modifier(system) is not None

    def execute(self, context):
        system = _get_active_system(context)
        if geonodes_utils.get_wind_modifier(system) is not None:
            geonodes_utils.disable_wind(system)
        elif geonodes_utils.enable_wind(system) is None:
            self.report({'WARNING'}, "Turn on Use Instances first")
            return {'CANCELLED'}
        context.view_layer.update()
        _tag_redraw_viewport(context)
        return {'FINISHED'}


def _read_wind_clipboard(context):
    try:
        data = json.loads(context.scene.scatter_wind_clipboard or "null")
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or not isinstance(data.get("settings"), dict):
        return None
    return data


class SCATTER_OT_reset_wind(Operator):
    bl_idname = "scatter.reset_wind"
    bl_label = "Reset Wind"
    bl_description = "Set every wind setting back to its default"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return geonodes_utils.get_wind_modifier(_get_active_system(context)) is not None

    def execute(self, context):
        geonodes_utils.reset_wind(geonodes_utils.get_wind_modifier(_get_active_system(context)))
        _tag_redraw_viewport(context)
        return {'FINISHED'}


class SCATTER_OT_copy_wind(Operator):
    bl_idname = "scatter.copy_wind"
    bl_label = "Copy Wind Settings"
    bl_description = "Copy the wind settings so they can be pasted into another system"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return geonodes_utils.get_wind_modifier(_get_active_system(context)) is not None

    def execute(self, context):
        system = _get_active_system(context)
        modifier = geonodes_utils.get_wind_modifier(system)
        context.scene.scatter_wind_clipboard = json.dumps({
            "source": system.name,
            "source_curve": system.curve_obj.name,
            "settings": geonodes_utils.read_wind_settings(modifier),
        })
        self.report({'INFO'}, f"Copied the wind settings of '{system.name}'")
        return {'FINISHED'}


class SCATTER_OT_paste_wind(Operator):
    bl_idname = "scatter.paste_wind"
    bl_label = "Paste Wind Settings"
    bl_description = "Use the copied wind settings in this system (turns the wind on if needed)"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        system = _get_active_system(context)
        if geonodes_utils.get_system_instances_modifier(system) is None:
            return False
        clipboard = _read_wind_clipboard(context)
        return clipboard is not None and clipboard.get("source_curve") != system.curve_obj.name

    @classmethod
    def description(cls, context, properties):
        clipboard = _read_wind_clipboard(context)
        if clipboard is None:
            return cls.bl_description
        return f"{cls.bl_description}.\nCopied from {clipboard.get('source', '?')}"

    def execute(self, context):
        system = _get_active_system(context)
        modifier = geonodes_utils.get_wind_modifier(system) or geonodes_utils.enable_wind(system)
        if modifier is None:
            self.report({'WARNING'}, "Turn on Use Instances first")
            return {'CANCELLED'}
        geonodes_utils.write_wind_settings(modifier, _read_wind_clipboard(context)["settings"])
        context.view_layer.update()
        _tag_redraw_viewport(context)
        return {'FINISHED'}


classes = (
    SCATTER_OT_toggle_wind,
    SCATTER_OT_reset_wind,
    SCATTER_OT_copy_wind,
    SCATTER_OT_paste_wind,
)
