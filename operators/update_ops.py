"""Operators for the online update check."""
from bpy.types import Operator

from ..utils import updates as updates_utils


#----OPERATORS----
class SCATTER_OT_check_updates(Operator):
    bl_idname = "scatter.check_updates"
    bl_label = "Check Now"
    bl_description = "Ask the RAF Pictures website whether a newer RAF Scatter is available"

    @classmethod
    def poll(cls, context):
        return updates_utils.online_allowed() and not updates_utils.is_checking()

    def execute(self, context):
        updates_utils.start_check()
        return {'FINISHED'}


#----REGISTRATION----
classes = (
    SCATTER_OT_check_updates,
)


def register():
    updates_utils.register()


def unregister():
    updates_utils.unregister()
