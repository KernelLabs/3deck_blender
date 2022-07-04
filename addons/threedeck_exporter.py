import bpy
import os
from bpy.props import (StringProperty,
                       BoolProperty,
                       EnumProperty,
                       IntProperty,
                       CollectionProperty)
from bpy_extras.io_utils import ExportHelper
from bpy.types import Operator, Panel, AddonPreferences
from io_scene_gltf2.blender.exp import gltf2_blender_export
import urllib.request, requests, json 
from json.decoder import JSONDecodeError

bl_info = {
    "name": "THREEDeck Exporter",
    "author": "3Deck.io",
    "version": (1, 0),
    "blender": (2, 65, 0),
    "location": "3Deck",
    "description": "This allows you to export your blender scene directly as a 3Deck asset",
    "warning": "",
    "doc_url": "",
    "tracker_url": "",
    "category": "Object",
}

serverprefix = "https://3deck.io/"
# serverprefix = "http://localhost:3000/"

def printcon(data):
    for window in bpy.context.window_manager.windows:
        screen = window.screen
        for area in screen.areas:
            if area.type == 'CONSOLE':
                override = {'window': window, 'screen': screen, 'area': area}
                bpy.ops.console.scrollback_append(override, text=str(data), type="OUTPUT")       


class ThreeDeckExporter(AddonPreferences):
    # this must match the add-on name, use '__package__'
    # when defining this in a submodule of a python package.
    bl_idname = "threedeck_exporter"

    d3_overwrite: BoolProperty(
        name="Overwrite Existing",
        description="If this model exists in 3Deck, overwrite it",
        default=True,
    )
    
    d3_exportanimations: BoolProperty(
        name="Export Animations",
        description="Export animations in the model",
        default=True,
    )

    d3_email: StringProperty(
        name="Email Address",
        description="3Deck email address",
        default="",
    )
    
    d3_uploadcode: StringProperty(
        name="Upload Code",
        description="3Deck Blender Upload Code (Configure in 3Deck settings under Account)",
        default="",
    )

    def draw(self, context):
        layout = self.layout
        layout.label(text="This is a preferences view for our add-on")
        layout.prop(self, "d3_overwrite")
        layout.prop(self, "d3_exportanimations")
        layout.prop(self, "d3_email")
        layout.prop(self, "d3_uploadcode")


class THREED_export_main(Panel):
    bl_space_type = 'FILE_BROWSER'
    bl_region_type = 'TOOL_PROPS'
    bl_label = "Settings Panel"

    @classmethod
    def poll(cls, context):
        sfile = context.space_data
        operator = sfile.active_operator
        return operator.bl_idname == "EXPORT_SCENE_OT_3deck"

    def draw(self, context):
        layout = self.layout
#        layout.use_property_split = True
        layout.use_property_decorate = False  # No animation.

        sfile = context.space_data
        operator = sfile.active_operator

        layout.prop(operator, 'd3_overwrite')
        layout.prop(operator, "d3_exportanimations")
        layout.prop(operator, 'd3_modelname')
        layout.prop(operator, 'd3_email')
        layout.prop(operator, 'd3_uploadcode')
        


class Export3Deck(bpy.types.Operator, ExportHelper):
    """Export scene as glTF 2.0 file and upload to 3Deck"""
    bl_idname = 'export_scene.3deck'
    bl_label = 'Export to 3Deck'
    bl_options = {'PRESET'}
    filename_ext = '.glb'
    filter_glob: StringProperty(default='*.glb', options={'HIDDEN'})
    
    def __init__(self):
        pass
    
    # List of operator properties, the attributes will be assigned
    # to the class instance from the operator settings before calling.
    d3_overwrite: BoolProperty(
        name="Overwrite Existing",
        description="If this model exists in 3Deck, overwrite it",
        default=True,
    )

    d3_exportanimations: BoolProperty(
        name="Export Animations",
        description="Export animations in the model",
        default=True,
    )

    d3_modelname: StringProperty(
        name="Model Asset Name",
        description="Name for asset in 3Deck",
        default="",
    )    
        
    d3_email: StringProperty(
        name="Email Address",
        description="3Deck email address",
        default="",
    )
    
    d3_uploadcode: StringProperty(
        name="Upload Code",
        description="3Deck Blender Upload Code (Configure in 3Deck settings under Account)",
        default="",
    )

    def validateUploadCode(self, email, uploadcode, filename):
        try:
            url = requests.get(serverprefix + "api/assetupload/check/"+email+"/"+uploadcode+"/"+filename)
            jsresult = json.loads(url.text);
            if jsresult["result"] == "OK" :
                return jsresult["numassets"]
        except JSONDecodeError:
            pass
        return -1

    def exportGLB(self):
        printcon("Exporting temporary files to " + bpy.app.tempdir+"/export.glb")
        bpy.ops.export_scene.gltf(filepath=bpy.app.tempdir+"export.glb",check_existing=False, use_active_scene=True, use_visible=True, export_animations=self.d3_exportanimations, use_renderable=True,export_format="GLB", export_tangents=False, export_image_format="JPEG", export_cameras=False, export_lights=False)

        bpy.context.scene.render.filepath = bpy.app.tempdir+"thumb.png"
        bpy.context.scene.render.resolution_x = 800 #perhaps set resolution in code
        bpy.context.scene.render.resolution_y = 500
        bpy.ops.render.render(use_viewport = False, write_still=True)

        return bpy.app.tempdir

    def uploadFilesFromPath(self, uploadpath):
        printcon("Uploading from path " + uploadpath)
        try:
            url = serverprefix + 'mediaapi/blenderupload'
            multiple_files = [('scene', (self.d3_modelname, open(uploadpath + 'export.glb', 'rb'), 'model/gltf-binary')),
                                ('thumb', ('thumb.png', open(uploadpath + 'thumb.png', 'rb'), 'image/png'))]
            r = requests.post(url, data={"email":self.d3_email, "assettoken":self.d3_uploadcode, "fileid":self.d3_modelname, "overwrite": self.d3_overwrite}, files=multiple_files)
            jsresult = json.loads(r.text);
            if jsresult["result"] == "OK" :
                return ""
            if jsresult["result"] == "FAIL" :
                return jsresult["error"]
        except JSONDecodeError:
            pass        
        return "Unexpected result from server"
       
    
    def invoke(self, context, event):
        filepath = bpy.data.filepath
        filepath_split = os.path.split(filepath) #list with [path, name]         
        scenename = os.path.splitext(filepath_split[1])[0]
        if not scenename :
            self.report({"ERROR"}, "You must save this scene first before exporting")
            return {"CANCELLED"}        
        self.d3_modelname = scenename

        preferences = context.preferences
        addon_prefs = preferences.addons["threedeck_exporter"].preferences
        self.d3_email = addon_prefs.d3_email
        self.d3_uploadcode = addon_prefs.d3_uploadcode
        self.d3_overwrite = addon_prefs.d3_overwrite
        self.d3_exportanimations = addon_prefs.d3_exportanimations
        return ExportHelper.invoke(self, context, event)    

    def execute(self, context):
        printcon("Exporting")
        preferences = context.preferences
        addon_prefs = preferences.addons["threedeck_exporter"].preferences
        numassets = self.validateUploadCode(self.d3_email, self.d3_uploadcode, self.d3_modelname)
        if numassets < 0 :
            self.report({"ERROR"}, "Unable to validate your email address and asset token. Ensure you have set the correct values from 3Deck settings.")
            return {'FINISHED'}
        uploadpath = self.exportGLB()
        # scene has been exported, now upload it
        uploadresult = self.uploadFilesFromPath(uploadpath)
        if (uploadresult):
            self.report({"ERROR"}, uploadresult)
        else :
            self.report({"INFO"}, "Your model was uploaded, and will appear in the 3Deck assets")
        return {'FINISHED'}
    
    def draw(self, context):
        pass

   
classes = (
    Export3Deck,
    THREED_export_main,
    ThreeDeckExporter,
#    Export3Deck_Base,
#    Export3Deck_Base2,
)

def menu_func(self, context):
    self.layout.operator(Export3Deck.bl_idname, text="Export to 3Deck")


def register():
    for c in classes:
        bpy.utils.register_class(c)    
    bpy.types.TOPBAR_MT_file_export.append(menu_func)
     

def unregister():
    for c in classes:
        bpy.utils.unregister_class(c)

    # remove from the export / import menu
    bpy.types.TOPBAR_MT_file_export.remove(menu_func)

register()
