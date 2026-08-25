# qgis2djipilot2
QGIS Toolbox that convert manually drawn flight plan so that it can follow DTM terrain and exported as a readable KML for DJI Pilot 2, with a proper parameter form:
    - Input flight line layer
    - DTM raster
    - User inputted Flying height (AGL)

HOW TO INSTALL
--------------
1. Open QGIS.
2. Processing menu -> Toolbox (or Ctrl+Alt+T).
3. At the top of the Toolbox panel, click the Python icon (scripts)
   dropdown -> "Add Script to Toolbox..." and select this file.
   (Or just copy this file into your QGIS "scripts" folder:
   Settings -> User Profiles -> Open active profile folder ->
   processing/scripts/)
4. The tool will appear under Processing Toolbox -> Scripts ->
   QGIS2DJIPilot2 Flight Planning -> Follow Terrain Flight Line.
5. Double-click it to open the normal QGIS algorithm dialog with
   dropdowns for layer/raster and fields for height, etc.
