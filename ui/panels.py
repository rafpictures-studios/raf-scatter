from bpy.types import Panel

from ..utils import geonodes as geonodes_utils


class SCATTER_PT_main(Panel):
    bl_idname = "SCATTER_PT_main"
    bl_label = "RAF Scatter"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "RAF Scatter"

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        header, panel = layout.panel("SCATTER_ground_panel", default_closed=False)
        header.label(text="Target Ground", icon='MESH_GRID')
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
            header.label(text="Manual Mode", icon='BRUSHES_ALL')
            if panel:
                self.draw_manual_controls(panel, scene)
        else:
            header, panel = layout.panel("SCATTER_procedural_panel", default_closed=False)
            header.label(text="Procedural Distribution", icon='GEOMETRY_NODES')
            if panel:
                self.draw_procedural_controls(panel, system)

        layout.separator(factor=0.4)
        header, panel = layout.panel("SCATTER_effectors_panel", default_closed=False)
        header.label(text=f"Effectors ({len(system.effectors)})", icon='MODIFIER_DATA')
        if panel:
            self.draw_effectors(panel, system)

    def draw_ground_section(self, layout, scene):
        if len(scene.scatter_grounds) == 0:
            row = layout.row()
            row.scale_y = 1.4
            row.operator("scatter.add_ground_popup", text="Add Ground", icon='ADD')

            row2 = layout.row()
            row2.scale_y = 1.4
            row2.operator("scatter.add_ground_from_selected", text="Add Selected as Ground", icon='IMPORT')
            return

        idx = scene.active_ground_index
        active_name = scene.scatter_grounds[idx].name if 0 <= idx < len(scene.scatter_grounds) else ""

        row = layout.row(align=True)
        row.menu("SCATTER_MT_grounds", text=active_name, icon='OUTLINER_OB_MESH')
        row.operator("scatter.add_ground_popup", text="", icon='ADD')
        row.operator("scatter.delete_ground", text="", icon='TRASH')

        row2 = layout.row()
        row2.scale_y = 1.2
        row2.operator("scatter.add_ground_from_selected", text="Add Selected as Ground", icon='IMPORT')

    def draw_systems_section(self, layout, ground):
        box = layout.box()
        row = box.row()
        row.template_list(
            "SCATTER_UL_systems", "", ground, "scatter_systems",
            ground, "active_scatter_system_index", rows=3,
        )
        side = row.column(align=True)
        side.menu("SCATTER_MT_add_system_type", icon='ADD', text="")
        side.operator("scatter.remove_system", icon='REMOVE', text="")

    def draw_manual_controls(self, layout, scene):
        is_active = scene.scatter_manual_mode_on
        label = "Stop Painting" if is_active else "Start Painting"
        icon = 'X' if is_active else 'BRUSHES_ALL'

        row = layout.row()
        row.scale_y = 1.8
        row.alert = is_active
        row.operator(
            "scatter.toggle_manual_mode", text=label, icon=icon,
            depress=is_active,
        )

        layout.separator(factor=0.3)
        layout.template_icon_view(scene, "scatter_active_brush", show_labels=True, scale=6.0)

    def draw_procedural_controls(self, layout, system):
        modifier = geonodes_utils.get_procedural_modifier(system)
        if modifier is None:
            layout.label(text="Procedural modifier not found")
            return

        col = layout.column()
        col.use_property_split = True
        col.use_property_decorate = False

        for socket_name in ("Distribute", "Density", "Seed"):
            prop_path = geonodes_utils.get_modifier_input_path(modifier, socket_name)
            if prop_path is None:
                col.label(text=f"{socket_name} socket not found")
                continue
            col.prop(modifier, prop_path, text=socket_name)

            # PENDING VERIFICATION: Distance Min only applies to Poisson
            # Disk. Requires a "Distance Min" socket (Float, subtype
            # DISTANCE) on gn_proceduralScatter_points in
            # resources/node_groups.blend (author's task in Blender, per
            # Rule H -- hide_in_modifier checked). Menu index 1 is
            # assumed to be "Poisson Disk" per the Section 7 table order
            # -- confirm the real stored value in the Python console
            # (print modifier["<Distribute socket id>"]) after switching
            # the dropdown, and adjust the comparison below if it differs.
            if socket_name == "Distribute" and geonodes_utils.get_modifier_input_value(modifier, "Distribute") == 1:
                distance_prop_path = geonodes_utils.get_modifier_input_path(modifier, "Distance Min")
                if distance_prop_path is None:
                    col.label(text="Distance Min socket not found")
                else:
                    col.prop(modifier, distance_prop_path, text="Distance Min")

        layout.separator(factor=0.5)

        instances_modifier = geonodes_utils.get_instances_modifier(system)
        is_active = instances_modifier is not None

        row = layout.row()
        row.scale_y = 1.4
        row.alert = is_active
        row.operator(
            "scatter.toggle_procedural_instances",
            text="Remove Instances" if is_active else "Use Instances",
            icon='X' if is_active else 'ADD',
            depress=is_active,
        )

        if instances_modifier is None:
            return

        col2 = layout.column()
        col2.use_property_split = True
        col2.use_property_decorate = False

        instances_prop_path = geonodes_utils.get_modifier_input_path(instances_modifier, "Instances")
        if instances_prop_path is None:
            col2.label(text="Instances socket not found")
            return
        col2.prop(instances_modifier, instances_prop_path, text="Instances")

        # PENDING VERIFICATION: same caveat as Distribute above -- menu
        # index assumed to follow the Section 7 table order (0 = Object,
        # 1 = Collection). Confirm the real stored value in the Python
        # console and adjust the comparison below if it differs.
        instances_value = geonodes_utils.get_modifier_input_value(instances_modifier, "Instances")
        socket_name = "Object" if instances_value == 0 else "Collection"
        prop_path = geonodes_utils.get_modifier_input_path(instances_modifier, socket_name)
        if prop_path is None:
            col2.label(text=f"{socket_name} socket not found")
        else:
            col2.prop(instances_modifier, prop_path, text=socket_name)

    def draw_effectors(self, layout, system):
        box = layout.box()
        row = box.row()
        row.template_list(
            "SCATTER_UL_effectors", "", system, "effectors",
            system, "active_effector_index", rows=3,
        )
        side = row.column(align=True)
        side.operator("scatter.add_effector_popup", icon='ADD', text="")
        side.operator("scatter.remove_effector", icon='REMOVE', text="")

        side.separator(factor=1.0)

        move_up = side.operator("scatter.move_effector", icon='TRIA_UP', text="")
        move_up.direction = 'UP'
        move_down = side.operator("scatter.move_effector", icon='TRIA_DOWN', text="")
        move_down.direction = 'DOWN'

        idx = system.active_effector_index
        if not (0 <= idx < len(system.effectors)):
            return

        effector = system.effectors[idx]

        detail = box.column()
        detail.separator(factor=0.3)
        detail.prop(effector, "name", text="", icon='MODIFIER_DATA')

        col = detail.column()
        col.use_property_split = True
        col.use_property_decorate = False
        col.prop(effector, "density", slider=True)
        col.prop(effector, "scale_variance", slider=True)


classes = (
    SCATTER_PT_main,
)