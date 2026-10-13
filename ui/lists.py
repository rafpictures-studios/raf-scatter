"""UI lists for scatter systems and effectors."""
from bpy.types import UIList

from ..preferences import get_addon_prefs, is_biome_in_group
from ..properties import EFFECTOR_ICON_NAMES, EFFECTOR_TYPE_ICONS
from ..utils import geonodes as geonodes_utils
from ..utils import icons as icon_utils


_NAME_SPLIT_FACTOR = 0.7


class SCATTER_UL_systems(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        menu_icon = icon_utils.get_menu_icon_id(item.system_type.lower())
        if menu_icon:
            row.prop(item, "name", text="", icon_value=menu_icon, emboss=False)
        else:
            icon_name = 'BRUSH_DATA' if item.system_type == 'MANUAL' else 'MOD_PARTICLES'
            row.prop(item, "name", text="", icon=icon_name, emboss=False)
        if item.curve_obj is None:
            return
        vis = row.row(align=True)
        view_props = vis.operator(
            "scatter.toggle_curve_visibility", text="", emboss=False,
            icon='RESTRICT_VIEW_ON' if item.curve_obj.hide_viewport else 'RESTRICT_VIEW_OFF',
        )
        view_props.mode = 'VIEWPORT'
        view_props.system_index = index
        render_props = vis.operator(
            "scatter.toggle_curve_visibility", text="", emboss=False,
            icon='RESTRICT_RENDER_ON' if item.curve_obj.hide_render else 'RESTRICT_RENDER_OFF',
        )
        render_props.mode = 'RENDER'
        render_props.system_index = index


class SCATTER_UL_effectors(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        split = layout.split(factor=_NAME_SPLIT_FACTOR, align=True)
        thumbnail_name = EFFECTOR_ICON_NAMES.get(item.effector_type)
        menu_icon = icon_utils.get_menu_icon_id(thumbnail_name)
        # an operator (not the name field) so the click can read Shift / Ctrl, like the Outliner
        name_row = split.row(align=True)
        name_row.alignment = 'LEFT'
        # with several effectors selected, unselected rows are dimmed; the list highlights the active
        if not item.selected and sum(1 for effector in data.effectors if effector.selected) > 1:
            name_row.active = False
        if menu_icon:
            op = name_row.operator(
                "scatter.select_effector", text=item.name, icon_value=menu_icon, emboss=False,
            )
        else:
            op = name_row.operator(
                "scatter.select_effector", text=item.name,
                icon=EFFECTOR_TYPE_ICONS.get(item.effector_type, 'MODIFIER_DATA'), emboss=False,
            )
        op.effector_index = index
        modifier = geonodes_utils.get_effector_modifier(data, item)
        if modifier is None:
            return
        vis = split.row(align=True)
        vis.alignment = 'RIGHT'
        view_props = vis.operator(
            "scatter.toggle_effector_visibility", text="", emboss=False,
            icon='RESTRICT_VIEW_ON' if not modifier.show_viewport else 'RESTRICT_VIEW_OFF',
        )
        view_props.mode = 'VIEWPORT'
        view_props.effector_index = index
        render_props = vis.operator(
            "scatter.toggle_effector_visibility", text="", emboss=False,
            icon='RESTRICT_RENDER_ON' if not modifier.show_render else 'RESTRICT_RENDER_OFF',
        )
        render_props.mode = 'RENDER'
        render_props.effector_index = index


class SCATTER_UL_biomes(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        thumbnail = icon_utils.get_biome_icon_id(item.name)
        if not item.valid:
            row.label(text=item.label, icon='ERROR')
        elif thumbnail:
            row.label(text=item.label, icon_value=thumbnail)
        else:
            row.label(text=item.label, icon='ASSET_MANAGER')
        detail = row.row()
        detail.alignment = 'RIGHT'
        detail.active = False
        if item.pack_id:
            detail.label(text=item.pack_name, icon='PACKAGE')
        else:
            detail.label(text=item.created.split("T")[0])

    def filter_items(self, context, data, propname):
        """Show only the biomes of the group picked in the preferences."""
        items = getattr(data, propname)
        prefs = get_addon_prefs(context)
        group = prefs.biome_group if prefs else None
        needle = self.filter_name.lower()
        flags = []
        for item in items:
            shown = group is None or is_biome_in_group(item, group)
            shown = shown and (not needle or needle in item.label.lower())
            flags.append(self.bitflag_filter_item if shown else 0)
        return flags, []


classes = (
    SCATTER_UL_systems,
    SCATTER_UL_effectors,
    SCATTER_UL_biomes,
)