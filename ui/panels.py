from bpy.types import Panel

from ..operators.brush_ops import BRUSH_ICONS, BRUSH_ITEMS


class SCATTER_PT_main(Panel):
    bl_idname = "SCATTER_PT_main"
    bl_label = "RAF Scatter"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Scatter"

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        header, panel = layout.panel("SCATTER_ground_panel", default_closed=False)
        header.label(text="Target Ground")
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
        header.label(text="Scatter System", icon='MOD_PARTICLES')
        if panel:
            self.draw_systems_section(panel, ground)

        sys_idx = ground.active_scatter_system_index
        if not (0 <= sys_idx < len(ground.scatter_systems)):
            return
        system = ground.scatter_systems[sys_idx]

        layout.separator(factor=0.4)
        if system.system_type == 'MANUAL':
            header, panel = layout.panel("SCATTER_manual_panel", default_closed=False)
            header.label(text="Manual Mode", icon='BRUSH_DATA')
            if panel:
                self.draw_manual_controls(panel, scene)
        else:
            header, panel = layout.panel("SCATTER_procedural_panel", default_closed=False)
            header.label(text="Procedural Distribution", icon='MOD_PARTICLES')
            if panel:
                self.draw_procedural_controls(panel, scene)

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
            return

        idx = scene.active_ground_index
        active_name = scene.scatter_grounds[idx].name if 0 <= idx < len(scene.scatter_grounds) else ""

        row = layout.row(align=True)
        row.menu("SCATTER_MT_grounds", text=active_name, icon='OUTLINER_OB_MESH')
        row.operator("scatter.add_ground_popup", text="", icon='ADD')
        row.operator("scatter.delete_ground", text="", icon='TRASH')

    def draw_systems_section(self, layout, ground):
        box = layout.box()
        row = box.row()
        row.template_list(
            "SCATTER_UL_systems", "", ground, "scatter_systems",
            ground, "active_scatter_system_index", rows=3,
        )
        side = row.column(align=True)
        side.menu("SCATTER_MT_add_system", icon='ADD', text="")
        side.operator("scatter.remove_system", icon='REMOVE', text="")

    def draw_manual_controls(self, layout, scene):
        icon = 'PAUSE' if scene.scatter_manual_mode_on else 'PLAY'
        label = "Sculpting Active" if scene.scatter_manual_mode_on else "Start Sculpting"
        layout.operator(
            "scatter.toggle_manual_mode", text=label, icon=icon,
            depress=scene.scatter_manual_mode_on,
        )

        grid = layout.grid_flow(row_major=True, columns=4, even_columns=True, align=True)
        for key, _label, _desc in BRUSH_ITEMS:
            cell = grid.column(align=True)
            cell.scale_y = 1.4
            op = cell.operator(
                "scatter.set_brush", text="", icon=BRUSH_ICONS[key],
                depress=(scene.scatter_active_brush == key),
            )
            op.brush = key

    def draw_procedural_controls(self, layout, scene):
        col = layout.column()
        col.use_property_split = True
        col.use_property_decorate = False
        col.prop(scene, "scatter_procedural_seed", text="Seed")
        layout.operator("scatter.regenerate_procedural", text="Regenerate", icon='FILE_REFRESH')

    def draw_effectors(self, layout, system):
        box = layout.box()
        row = box.row()
        row.template_list(
            "SCATTER_UL_effectors", "", system, "effectors",
            system, "active_effector_index", rows=3,
        )
        side = row.column(align=True)
        side.operator("scatter.add_effector", icon='ADD', text="")
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