from bpy.types import UIList

from ..properties import EFFECTOR_TYPE_ICONS


class SCATTER_UL_systems(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        icon_name = 'BRUSH_DATA' if item.system_type == 'MANUAL' else 'MOD_PARTICLES'
        row.prop(item, "name", text="", icon=icon_name, emboss=False)

        if item.curve_obj is not None:
            vis = row.row(align=True)
            vis.prop(
                item.curve_obj, "hide_viewport", text="", emboss=False,
                icon='RESTRICT_VIEW_ON' if item.curve_obj.hide_viewport else 'RESTRICT_VIEW_OFF',
            )
            vis.prop(
                item.curve_obj, "hide_render", text="", emboss=False,
                icon='RESTRICT_RENDER_ON' if item.curve_obj.hide_render else 'RESTRICT_RENDER_OFF',
            )


class SCATTER_UL_effectors(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        icon_name = EFFECTOR_TYPE_ICONS.get(item.effector_type, 'MODIFIER_DATA')
        row.prop(item, "name", text="", icon=icon_name, emboss=False)


classes = (
    SCATTER_UL_systems,
    SCATTER_UL_effectors,
)