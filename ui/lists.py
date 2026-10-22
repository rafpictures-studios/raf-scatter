"""UI lists for scatter systems and effectors."""
from bpy.types import UIList

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


class SCATTER_UL_biome_rows(UIList):
    """Grouped biome list: My Biomes, then one header per installed pack."""

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        if item.kind in {'HEADER_LOCAL', 'HEADER_PACK'}:
            row.label(text=item.name, icon='HOME' if item.kind == 'HEADER_LOCAL' else 'PACKAGE')
            detail = row.row()
            detail.alignment = 'RIGHT'
            detail.active = False
            detail.label(text=item.detail)
            return
        row.separator(factor=2.0)
        if item.kind == 'EMPTY':
            row.active = False
            row.label(text=item.name)
            return
        biome = data.scatter_biomes[item.biome_index]
        thumbnail = icon_utils.get_biome_icon_id(biome.name)
        if not biome.valid:
            row.label(text=biome.label, icon='ERROR')
        elif thumbnail:
            row.label(text=biome.label, icon_value=thumbnail)
        else:
            row.label(text=biome.label, icon='ASSET_MANAGER')
        detail = row.row()
        detail.alignment = 'RIGHT'
        detail.active = False
        if biome.pack_id:
            detail.label(text="", icon='LOCKED')
        else:
            detail.label(text=biome.created.split("T")[0])

    def filter_items(self, context, data, propname):
        """Keep the group order; a name filter keeps matching biomes and their headers."""
        rows = getattr(data, propname)
        needle = self.filter_name.lower()
        if not needle:
            return [self.bitflag_filter_item] * len(rows), []
        flags = [self.bitflag_filter_item if row.kind != 'BIOME' or needle in row.name.lower()
                 else 0 for row in rows]
        return flags, []

classes = (
    SCATTER_UL_systems,
    SCATTER_UL_effectors,
    SCATTER_UL_biome_rows,
)