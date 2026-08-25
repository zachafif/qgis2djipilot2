"""
Follow Terrain Flight Line Generator - QGIS Processing Tool
Created by Zachary Afif
"""

from qgis.PyQt.QtCore import QCoreApplication
from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterVectorLayer,
    QgsProcessingParameterRasterLayer,
    QgsProcessingParameterNumber,
    QgsProcessingParameterFileDestination,
    QgsProcessingUtils,
)
import processing
import os


class FollowTerrainAlgorithm(QgsProcessingAlgorithm):

    INPUT = 'INPUT'
    DTM = 'DTM'
    HEIGHT = 'HEIGHT'
    MAX_DIST = 'MAX_DIST'
    OUTPUT = 'OUTPUT'

    def tr(self, string):
        return QCoreApplication.translate('FollowTerrainAlgorithm', string)

    def createInstance(self):
        return FollowTerrainAlgorithm()

    def name(self):
        return 'followterrainflightline'

    def displayName(self):
        return self.tr('Follow Terrain Flight Line')

    def group(self):
        return self.tr('QGIS2DJIPilot2 Flight Planning')

    def groupId(self):
        return 'dji_flight_planning'

    def shortHelpString(self):
        return self.tr(
            "Generates a terrain-following flight line KML for DJI Pilot 2.\n\n"
            "Splits the input line(s) into short segments, drapes them onto a "
            "DTM, and writes an absolute-altitude KML path that maintains a "
            "constant height above ground (AGL)."
        )

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterVectorLayer(
                self.INPUT,
                self.tr('Input flight line layer'),
                [QgsProcessing.TypeVectorLine]
            )
        )
        self.addParameter(
            QgsProcessingParameterRasterLayer(
                self.DTM,
                self.tr('DTM (elevation raster)')
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.HEIGHT,
                self.tr('Flying height above ground (m)'),
                type=QgsProcessingParameterNumber.Double,
                defaultValue=50.0,
                minValue=0.0,
                maxValue=500.0
            )
        )
        max_dist_param = QgsProcessingParameterNumber(
            self.MAX_DIST,
            self.tr('Max segment length (map units, e.g. degrees for lat/long layers)'),
            type=QgsProcessingParameterNumber.Double,
            defaultValue=0.00045045,
            minValue=0.0000001
        )
        max_dist_param.setFlags(max_dist_param.flags() | QgsProcessingParameterNumber.FlagAdvanced)
        self.addParameter(max_dist_param)

        self.addParameter(
            QgsProcessingParameterFileDestination(
                self.OUTPUT,
                self.tr('Output KML file'),
                fileFilter='KML files (*.kml)'
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        layer = self.parameterAsVectorLayer(parameters, self.INPUT, context)
        dtm = self.parameterAsRasterLayer(parameters, self.DTM, context)
        fly_height = self.parameterAsDouble(parameters, self.HEIGHT, context)
        max_dist = self.parameterAsDouble(parameters, self.MAX_DIST, context)
        output_path = self.parameterAsFileOutput(parameters, self.OUTPUT, context)

        if layer is None:
            raise QgsProcessingException(self.tr('Invalid input layer'))
        if dtm is None:
            raise QgsProcessingException(self.tr('Invalid DTM raster'))

        input_layer_source = layer.dataProvider().dataSourceUri()

        feedback.pushInfo('Checking for existing "fid" field...')
        fields = layer.fields()
        fid_index = fields.indexOf('fid')
        if fid_index != -1:
            feedback.pushInfo('Removing "fid" field to avoid SQLite key conflicts...')
            alg_params = {
                'COLUMN': ['fid'],
                'INPUT': layer,
                'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
            }
            clean_input = processing.run(
                'native:deletecolumn', alg_params,
                context=context, feedback=feedback, is_child_algorithm=True
            )['OUTPUT']
        else:
            clean_input = layer

        feedback.setProgress(15)
        feedback.pushInfo('Splitting lines by max length ({})...'.format(max_dist))
        alg_params = {
            'INPUT': clean_input,
            'LENGTH': max_dist,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        splitted = processing.run(
            'native:splitlinesbylength', alg_params,
            context=context, feedback=feedback, is_child_algorithm=True
        )['OUTPUT']

        feedback.setProgress(35)
        feedback.pushInfo('Draping lines onto DTM...')
        alg_params = {
            'BAND': 1,
            'INPUT': splitted,
            'NODATA': 0,
            'RASTER': dtm,
            'SCALE': 1,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        draped = processing.run(
            'native:setzfromraster', alg_params,
            context=context, feedback=feedback, is_child_algorithm=True
        )['OUTPUT']

        feedback.setProgress(55)
        feedback.pushInfo('Extracting Z values...')
        alg_params = {
            'COLUMN_PREFIX': 'z_',
            'INPUT': draped,
            'SUMMARIES': [4],  # mean
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        zval = processing.run(
            'native:extractzvalues', alg_params,
            context=context, feedback=feedback, is_child_algorithm=True
        )['OUTPUT']

        feedback.setProgress(70)
        feedback.pushInfo('Building coordinate list...')

        # `zval` here is a layer reference (string/ID), not a live layer object,
        # because it came out of a child algorithm run with is_child_algorithm=True.
        # Resolve it into an actual QgsVectorLayer before reading features from it.
        zval_layer = QgsProcessingUtils.mapLayerFromString(zval, context)
        if zval_layer is None:
            raise QgsProcessingException(self.tr('Could not load intermediate layer with extracted Z values.'))

        coords = []
        features = list(zval_layer.getFeatures())

        if not features:
            raise QgsProcessingException(self.tr('No features found after processing input layer.'))

        def get_3d_points(geom):
            return list(geom.vertices())

        first_pts = get_3d_points(features[0].geometry())
        if not first_pts:
            raise QgsProcessingException(self.tr('First feature has no vertices.'))
        hp_z = first_pts[0].z()

        total = len(features)
        for i, feat in enumerate(features):
            if feedback.isCanceled():
                break
            pts = get_3d_points(feat.geometry())
            if pts:
                pt = pts[0]
                zc = (pt.z() - hp_z) + fly_height
                coords.append(f"{pt.x():.6f},{pt.y():.6f},{zc:.6f}")
            feedback.setProgress(70 + int(20 * (i + 1) / total))

        last_pts = get_3d_points(features[-1].geometry())
        if last_pts:
            lpt = last_pts[-1]
            lzc = (lpt.z() - hp_z) + fly_height
            coords.append(f"{lpt.x():.6f},{lpt.y():.6f},{lzc:.6f}")

        coords_str = " ".join(coords)

        flight_name = os.path.splitext(os.path.basename(output_path))[0]

        kml_template = f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2" xmlns:gx="http://www.google.com/kml/ext/2.2" xmlns:kml="http://www.opengis.net/kml/2.2" xmlns:atom="http://www.w3.org/2005/Atom">
<Document>
	<name>{flight_name}.kml</name>
	<Style id="line1">
		<LineStyle>
			<color>ff0000ff</color>
			<width>2</width>
		</LineStyle>
	</Style>
	<Placemark>
		<name>{flight_name}</name>
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

        feedback.setProgress(95)
        with open(output_path, 'w') as kml_file:
            kml_file.write(kml_template)

        feedback.pushInfo('KML file saved to: {}'.format(os.path.abspath(output_path)))
        feedback.setProgress(100)

        return {self.OUTPUT: output_path}