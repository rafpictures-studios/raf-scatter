from bpy.types import UIList


class SCATTER_UL_systems(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        icon_name = 'BRUSH_DATA' if item.system_type == 'MANUAL' else 'MOD_PARTICLES'
        row.prop(item, "name", text="", icon=icon_name, emboss=False)


class SCATTER_UL_effectors(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        # No expand/collapse toggle here — guide Rule D: the active
        # effector's detail panel below the list is always shown open.
        row.prop(item, "name", text="", icon='MODIFIER_DATA', emboss=False)


classes = (
    SCATTER_UL_systems,
    SCATTER_UL_effectors,
)
