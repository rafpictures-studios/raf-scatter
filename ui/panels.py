"""Main N-panel for RAF Scatter."""
from bpy.types import Panel

from ..utils import geonodes as geonodes_utils
from ..utils import icons as icon_utils


#----SOCKET ROWS----
def _draw_socket_row(col, modifier, socket_name, prop_path):
    """Draw a socket field; Seed sockets get an icon-only random seed button."""
    if socket_name != "Seed":
        col.prop(modifier, prop_path, text=socket_name)
        return
    row = col.row(align=True)
    row.prop(modifier, prop_path, text=socket_name)
    seed_icon = icon_utils.get_menu_icon_id("seed")
    if seed_icon:
        op = row.operator("scatter.randomize_seed", text="", icon_value=seed_icon)
    else:
        op = row.operator("scatter.randomize_seed", text="", icon='FILE_REFRESH')
    op.modifier_name = modifier.name
    op.socket_name = socket_name


#----MAIN PANEL----
class SCATTER_PT_main(Panel):
    bl_idname = "SCATTER_PT_main"
    bl_label = "RAF Scatter"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "RAF Scatter"

    def draw_header(self, context):
        logo_icon = icon_utils.get_menu_icon_id("raf_scatter_logo")
        if logo_icon is not None:
            self.layout.label(icon_value=logo_icon)

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        header, panel = layout.panel("SCATTER_ground_panel", default_closed=False)
        header.label(text="Target Ground", icon='OUTLINER_OB_MESH')
        if panel:
            self.draw_ground_section(panel, scene)
        if len(scene.scatter_grounds) == 0:
            return
        idx = scene.active_ground_index
        if not (0 <= idx < len(scene.scatter_grounds)):
            return
        ground = scene.scatter_grounds[idx]
        layout.separator(factor=0.4)
        header, panel = layout.panel("SCATTER_systems_panel", default_closed=False)
        header.label(text="Scatter System", icon='OUTLINER_OB_CURVES')
        if panel:
            self.draw_systems_section(panel, ground)
        sys_idx = ground.active_scatter_system_index
        if not (0 <= sys_idx < len(ground.scatter_systems)):
            return
        system = ground.scatter_systems[sys_idx]
        layout.separator(factor=0.4)
        if system.system_type == 'MANUAL':
            header, panel = layout.panel("SCATTER_manual_panel", default_closed=False)
            header.label(text="Paint Mode", icon='BRUSHES_ALL')
            if panel:
                self.draw_manual_controls(panel, scene, system)
        else:
            header, panel = layout.panel("SCATTER_procedural_panel", default_closed=False)
            header.label(text="Procedural Mode", icon='GEOMETRY_NODES')
            if panel:
                self.draw_procedural_controls(panel, system)
        layout.separator(factor=0.4)
        header, panel = layout.panel("SCATTER_effectors_panel", default_closed=True)
        header.label(text=f"Masks ({len(system.effectors)})", icon='MODIFIER_DATA')
        if panel:
            self.draw_effectors(panel, system)

    def draw_ground_section(self, layout, scene):
        if len(scene.scatter_grounds) == 0:
            row = layout.row()
            row.scale_y = 1.4
            row.operator("scatter.add_ground_popup", text="Add Ground", icon='ADD')
            row2 = layout.row()
            row2.scale_y = 1.2
            row2.operator(
                "scatter.add_ground_from_selected", text="Add Selected as Ground", icon='IMPORT',
            )
            return
        grounds = scene.scatter_grounds
        idx = scene.active_ground_index
        active_name = grounds[idx].name if 0 <= idx < len(grounds) else ""
        row = layout.row(align=True)
        row.menu("SCATTER_MT_grounds", text=active_name, icon='OUTLINER_OB_MESH')
        row.operator("scatter.select_ground", text="", icon='RESTRICT_SELECT_OFF')
        row.operator("scatter.add_ground_popup", text="", icon='ADD')
        row.operator("scatter.delete_ground", text="", icon='TRASH')
        row2 = layout.row()
        row2.scale_y = 1.2
        row2.operator(
            "scatter.add_ground_from_selected", text="Add Selected as Ground", icon='IMPORT',
        )

    def draw_systems_section(self, layout, ground):
        box = layout.box()
        row = box.row()
        row.template_list(
            "SCATTER_UL_systems", "", ground, "scatter_systems",
            ground, "active_scatter_system_index", rows=5,
        )
        side = row.column(align=True)
        add_op = side.operator("wm.call_menu", icon='ADD', text="")
        add_op.name = "SCATTER_MT_add_system_type"
        side.operator("scatter.remove_system", icon='REMOVE', text="")
        side.operator("scatter.duplicate_system", icon='DUPLICATE', text="")
        side.separator(factor=1.0)
        side.operator("scatter.open_biome_browser", icon='ASSET_MANAGER', text="")
        side.operator("scatter.open_biome_preferences", icon='PREFERENCES', text="")

    def draw_manual_controls(self, layout, scene, system):
        curve_obj = system.curve_obj
        is_active = (
            scene.scatter_paint_ui_saved
            and curve_obj is not None
            and scene.scatter_paint_curve_obj == curve_obj
            and curve_obj.mode == 'SCULPT_CURVES'
        )
        label = "Stop Painting" if is_active else "Start Painting"
        icon = 'X' if is_active else 'BRUSHES_ALL'
        row = layout.row()
        row.scale_y = 1.8
        row.alert = is_active
        row.operator("scatter.start_manual_paint", text=label, icon=icon, depress=is_active)
        layout.separator(factor=0.5)
        instances_modifier = geonodes_utils.get_manual_instances_modifier(system)
        if instances_modifier is None:
            row = layout.row()
            row.scale_y = 1.4
            row.operator(
                "scatter.toggle_manual_instances", text="Use Instances",
                icon='OUTLINER_OB_GROUP_INSTANCE',
            )
            return
        row = layout.row(align=True)
        row.scale_y = 1.4
        row.operator("scatter.open_library", text="Open Library", icon='COLLECTION_NEW')
        row.operator("scatter.open_preferences", text="", icon='PREFERENCES')
        col2 = layout.column()
        col2.use_property_split = True
        col2.use_property_decorate = False
        instances_value = geonodes_utils.get_modifier_input_value(
            instances_modifier, "Instances", 0,
        )
        source_label = "Object" if instances_value == 0 else "Collection"
        col2.operator_menu_enum(
            "scatter.set_manual_instances_source", "source", text=source_label,
        )
        if instances_value == 0:
            col2.prop(system, "manual_instances_object")
        else:
            col2.prop(system, "manual_instances_collection")
        for socket_name in (
            "Seed", "Scale Min", "Scale Max", "Random Rotation", "Translation", "Local Space",
        ):
            prop_path = geonodes_utils.get_modifier_input_path(instances_modifier, socket_name)
            if prop_path is None:
                col2.label(text=f"{socket_name} socket not found")
            else:
                _draw_socket_row(col2, instances_modifier, socket_name, prop_path)
        if len(system.effectors) > 0:
            for socket_name in ("Edge Falloff", "Falloff"):
                prop_path = geonodes_utils.get_modifier_input_path(instances_modifier, socket_name)
                if prop_path is None:
                    col2.label(text=f"{socket_name} socket not found")
                    continue
                col2.prop(instances_modifier, prop_path, text=socket_name)

    def draw_procedural_controls(self, layout, system):
        modifier = geonodes_utils.get_procedural_modifier(system)
        if modifier is None:
            layout.label(text="Procedural modifier not found")
            return
        col = layout.column()
        col.use_property_split = True
        col.use_property_decorate = False
        for socket_name in ("Density", "Distance Min", "Seed"):
            prop_path = geonodes_utils.get_modifier_input_path(modifier, socket_name)
            if prop_path is None:
                col.label(text=f"{socket_name} socket not found")
            else:
                _draw_socket_row(col, modifier, socket_name, prop_path)
        layout.separator(factor=0.5)
        instances_modifier = geonodes_utils.get_instances_modifier(system)
        if instances_modifier is None:
            row = layout.row()
            row.scale_y = 1.4
            row.operator(
                "scatter.toggle_procedural_instances", text="Use Instances",
                icon='OUTLINER_OB_GROUP_INSTANCE',
            )
            return
        row = layout.row(align=True)
        row.scale_y = 1.4
        row.operator("scatter.open_library", text="Open Library", icon='COLLECTION_NEW')
        row.operator("scatter.open_preferences", text="", icon='PREFERENCES')
        col2 = layout.column()
        col2.use_property_split = True
        col2.use_property_decorate = False
        instances_value = geonodes_utils.get_modifier_input_value(
            instances_modifier, "Instances", 0,
        )
        source_label = "Object" if instances_value == 0 else "Collection"
        col2.operator_menu_enum(
            "scatter.set_instances_source", "source", text=source_label,
        )
        if instances_value == 0:
            col2.prop(system, "instances_object")
        else:
            col2.prop(system, "instances_collection")
        for socket_name in (
            "Align Surface", "Scale Min", "Scale Max", "Random Rotation", "Translation",
            "Local Space",
        ):
            prop_path = geonodes_utils.get_modifier_input_path(instances_modifier, socket_name)
            if prop_path is None:
                col2.label(text=f"{socket_name} socket not found")
                continue
            col2.prop(instances_modifier, prop_path, text=socket_name)
        if len(system.effectors) > 0:
            for socket_name in ("Edge Falloff", "Falloff"):
                prop_path = geonodes_utils.get_modifier_input_path(instances_modifier, socket_name)
                if prop_path is None:
                    col2.label(text=f"{socket_name} socket not found")
                    continue
                col2.prop(instances_modifier, prop_path, text=socket_name)

    def draw_effectors(self, layout, system):
        box = layout.box()
        row = box.row()
        row.template_list(
            "SCATTER_UL_effectors", "", system, "effectors",
            system, "active_effector_index", rows=5,
        )
        side = row.column(align=True)
        add_op = side.operator("wm.call_menu", icon='ADD', text="")
        add_op.name = "SCATTER_MT_add_effector"
        side.operator("scatter.remove_effector", icon='REMOVE', text="")
        side.operator("scatter.duplicate_effector", icon='DUPLICATE', text="")
        side.separator()
        side.operator("scatter.copy_effectors", icon='COPYDOWN', text="")
        side.operator("scatter.paste_effectors", icon='PASTEDOWN', text="")
        idx = system.active_effector_index
        if not (0 <= idx < len(system.effectors)):
            return
        effector = system.effectors[idx]
        modifier = geonodes_utils.get_effector_modifier(system, effector)
        if modifier is None or modifier.node_group is None:
            box.label(text="No controls", icon='INFO')
            return
        detail = box.column()
        detail.separator(factor=0.3)
        col = detail.column()
        col.use_property_split = True
        col.use_property_decorate = False
        if effector.effector_type == 'MASK_BY_TEXTURE':
            self._draw_texture_controls(col, modifier)
        elif effector.effector_type == 'MASK_BY_POSITION':
            self._draw_grouped_mask_controls(
                col, modifier, "Position",
                geonodes_utils.POSITION_BASE_SOCKETS,
                geonodes_utils.POSITION_EDGE_BLEND_SOCKETS,
            )
        elif effector.effector_type == 'MASK_BY_NORMAL':
            self._draw_grouped_mask_controls(
                col, modifier, "Slope",
                geonodes_utils.SLOPE_BASE_SOCKETS,
                geonodes_utils.SLOPE_EDGE_BLEND_SOCKETS,
            )
        elif effector.effector_type == 'GEOMETRY_PROXIMITY':
            self._draw_proximity_controls(col, system, effector, modifier)
        elif effector.effector_type == 'MASK_BY_ATTRIBUTE':
            self._draw_vertex_controls(col, system, effector, modifier)

    def _draw_texture_controls(self, col, modifier):
        label = geonodes_utils.get_menu_socket_label(modifier, "Texture")
        visible_sockets = geonodes_utils.TEXTURE_SOCKETS_BY_OPTION.get(label)
        if visible_sockets is not None:
            col.operator_menu_enum("scatter.set_texture_option", "option", text=label)
            for socket in modifier.node_group.interface.items_tree:
                if socket.item_type != 'SOCKET' or socket.in_out != 'INPUT':
                    continue
                if socket.name in geonodes_utils.TEXTURE_INTERNAL_SOCKETS:
                    continue
                if socket.name not in visible_sockets:
                    continue
                prop_path = geonodes_utils.get_modifier_input_path(modifier, socket.name)
                if prop_path is None:
                    continue
                if socket.name == "Image":
                    img_row = col.row(align=True)
                    img_row.prop(modifier, prop_path, text="Image")
                    img_row.operator("scatter.open_mask_image", text="", icon='FILE_FOLDER')
                else:
                    _draw_socket_row(col, modifier, socket.name, prop_path)

    def _draw_proximity_controls(self, col, system, effector, modifier):
        """Draw proximity source pickers and the shared mask controls."""
        label_row = col.row()
        label_row.active = False
        label_row.label(text="Proximity")
        target_value = geonodes_utils.get_modifier_input_value(modifier, "Target", 0)
        source_label = "Object" if target_value == 0 else "Collection"
        col.operator_menu_enum("scatter.set_proximity_target", "source", text=source_label)
        if target_value == 0:
            col.prop(effector, "proximity_object")
        else:
            col.prop(effector, "proximity_collection")
        self._draw_socket_set(col, modifier, geonodes_utils.PROXIMITY_BASE_SOCKETS)
        col.separator(factor=0.3)
        edge_blend_value = geonodes_utils.get_modifier_input_value(modifier, "Edge Blend", False)
        edge_blend_on = bool(edge_blend_value)
        col.operator(
            "scatter.toggle_edge_blend", text="Edge Blend",
            icon='MOD_NOISE', depress=edge_blend_on,
        )
        if edge_blend_on:
            mode_prop_path = geonodes_utils.get_modifier_input_path(modifier, "Mode")
            if mode_prop_path is None:
                col.label(text="Mode socket not found")
            else:
                col.prop(modifier, mode_prop_path, text="Mode")
            self._draw_socket_set(col, modifier, geonodes_utils.PROXIMITY_EDGE_BLEND_SOCKETS)

    def _draw_vertex_controls(self, col, system, effector, modifier):
        """Draw vertex mask controls with a mode-based source block."""
        label_row = col.row()
        label_row.active = False
        label_row.label(text="Vertex Group")
        ground = system.target_ground
        mode_value = effector.vertex_mode
        mode_label = "Paint New" if mode_value == 0 else "Existing Group"
        col.operator_menu_enum("scatter.set_vertex_mode", "source", text=mode_label)
        if mode_value == 0:
            paint_row = col.row()
            paint_row.scale_y = 1.4
            painting = ground is not None and ground.mode == 'WEIGHT_PAINT'
            paint_row.alert = painting
            paint_row.operator(
                "scatter.start_vertex_paint",
                text="Stop Paint" if painting else "Start Paint",
                icon='X' if painting else 'BRUSH_DATA',
                depress=painting,
            )
        else:
            if ground is not None:
                col.prop_search(effector, "vertex_group_name", ground, "vertex_groups", text="")
            else:
                col.prop(effector, "vertex_group_name", text="")
        self._draw_socket_set(col, modifier, geonodes_utils.VERTEX_BASE_SOCKETS)
        col.separator(factor=0.3)
        edge_blend_value = geonodes_utils.get_modifier_input_value(modifier, "Edge Blend", False)
        edge_blend_on = bool(edge_blend_value)
        col.operator(
            "scatter.toggle_edge_blend", text="Edge Blend",
            icon='MOD_NOISE', depress=edge_blend_on,
        )
        if edge_blend_on:
            mode_prop_path = geonodes_utils.get_modifier_input_path(modifier, "Mode")
            if mode_prop_path is None:
                col.label(text="Mode socket not found")
            else:
                col.prop(modifier, mode_prop_path, text="Mode")
            self._draw_socket_set(col, modifier, geonodes_utils.VERTEX_EDGE_BLEND_SOCKETS)

    def _draw_grouped_mask_controls(self, col, modifier, group_label, base_sockets, edge_sockets):
        """Draw base sockets, an edge blend toggle, and edge sockets."""
        edge_blend_value = geonodes_utils.get_modifier_input_value(modifier, "Edge Blend", False)
        edge_blend_on = bool(edge_blend_value)
        label_row = col.row()
        label_row.active = False
        label_row.label(text=group_label)
        self._draw_socket_set(col, modifier, base_sockets)
        col.separator(factor=0.3)
        col.operator(
            "scatter.toggle_edge_blend", text="Edge Blend",
            icon='MOD_NOISE', depress=edge_blend_on,
        )
        if edge_blend_on:
            mode_prop_path = geonodes_utils.get_modifier_input_path(modifier, "Mode")
            if mode_prop_path is None:
                col.label(text="Mode socket not found")
            else:
                col.prop(modifier, mode_prop_path, text="Mode")
            self._draw_socket_set(col, modifier, edge_sockets)

    @staticmethod
    def _draw_socket_set(col, modifier, names):
        for socket in modifier.node_group.interface.items_tree:
            if socket.item_type != 'SOCKET' or socket.in_out != 'INPUT':
                continue
            if socket.name not in names:
                continue
            prop_path = geonodes_utils.get_modifier_input_path(modifier, socket.name)
            if prop_path is None:
                continue
            _draw_socket_row(col, modifier, socket.name, prop_path)


classes = (
    SCATTER_PT_main,
)