##Script For Creating Follow Terrain Flight Line for DJI Pilot 2
##Created by Zachary Afif 

from PyQt5.QtGui import *
import processing
import os

# Input
layer = iface.activeLayer()
input_layer = layer.dataProvider().dataSourceUri()
directory = 'c:/Users/tobias/Desktop/object1'
input_raster = QFileDialog.getOpenFileName(None, 'Open DTM file', directory, '*.tif')
fly_height, ok = QInputDialog.getInt(None, "Enter Flying Height", "Value:", 5, 50, 120)

dtm = QgsRasterLayer(input_raster[0], "DTM")
coords = []

# 1. Drop the existing 'fid' column if it exists to prevent SQLite duplicate key errors
fields = layer.fields()
fid_index = fields.indexOf('fid')
if fid_index != -1:
    alg_params = {
        'COLUMN': ['fid'],
        'INPUT': input_layer,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }
    clean_input = processing.run('native:deletecolumn', alg_params)['OUTPUT']
else:
    clean_input = input_layer

# 2. Split lines by maximum length
max_dist = 0.00045045
alg_params = {
    'INPUT': clean_input,
    'LENGTH': max_dist,
    'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
}
splitted = processing.run('native:splitlinesbylength', alg_params)['OUTPUT']

# 3. Drape (set Z value from raster)
alg_params = {
    'BAND': 1,
    'INPUT': splitted,
    'NODATA': 0,
    'RASTER': dtm,
    'SCALE': 1,
    'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
}
draped = processing.run('native:setzfromraster', alg_params)['OUTPUT']

# 4. Extract Z values directly into a temporary memory layer
alg_params = {
    'COLUMN_PREFIX': 'z_',
    'INPUT': draped,
    'SUMMARIES': [4],  # mean
    'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
}
zval = processing.run('native:extractzvalues', alg_params)['OUTPUT']

# 5. Extract coordinates using native PyQGIS with Z support
features = list(zval.getFeatures())

if features:
    # Helper function to get all 3D points from a feature geometry
    def get_3d_points(geom):
        return list(geom.vertices())

    # First point altitude baseline reference
    first_pts = get_3d_points(features[0].geometry())
    hp_z = first_pts[0].z()

    # Iterate features and extract the starting point of each line segment
    for feat in features:
        pts = get_3d_points(feat.geometry())
        if pts:
            pt = pts[0]
            zc = (pt.z() - hp_z) + fly_height
            coords.append(f"{pt.x():.6f},{pt.y():.6f},{zc:.6f}")

    # Add the final point of the very last line segment
    last_pts = get_3d_points(features[-1].geometry())
    if last_pts:
        lpt = last_pts[-1]
        lzc = (lpt.z() - hp_z) + fly_height
        coords.append(f"{lpt.x():.6f},{lpt.y():.6f},{lzc:.6f}")

coords_str = " ".join(coords)

kml_template = f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2" xmlns:gx="http://www.google.com/kml/ext/2.2" xmlns:kml="http://www.opengis.net/kml/2.2" xmlns:atom="http://www.w3.org/2005/Atom">
<Document>
	<name>Flight_EPEL_Trial.kml</name>
	<Style id="line1">
		<LineStyle>
			<color>ff0000ff</color>
			<width>2</width>
		</LineStyle>
	</Style>
	<Placemark>
		<name>Flight_EPEL_Trial</name>
		<description>Unclassified Line Feature</description>
		<styleUrl>#line1</styleUrl>
		<LineString>
			<altitudeMode>absolute</altitudeMode>
			<coordinates>
				{coords_str}
			</coordinates>
		</LineString>
	</Placemark>
</Document>
</kml>"""

kml_filename = input_layer.replace(".shp", ".kml")
with open(kml_filename, 'w') as kml_file:
    kml_file.write(kml_template)

print("KML file saved to: ", os.path.abspath(kml_filename))