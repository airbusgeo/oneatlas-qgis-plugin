import os

from qgis.PyQt.QtWidgets import QAction, QMessageBox, QRadioButton, QGridLayout, QGroupBox
from qgis.PyQt.QtGui import QIcon, QColor
from qgis.core import Qgis

from qgis.core import (
    QgsVectorLayer,
    QgsRasterLayer,
    QgsProject,
)

from .mySearch import MySearch

# Access class through python console
# my = qgis.utils.plugins['OneAtlas']

class OneAtlas:
    def __init__(self, iface):
        self.iface = iface
        self.menu = 'OneAtlas'
        self.toolbar = self.iface.addToolBar(self.menu)
        self.mySearch = None

        # Connect function who diable layer button
        self.iface.currentLayerChanged.connect(self.disableLayerBtnByLayerSelection)


    # Add action to toolbar
    def addAction(self, menu, icon, callback):
        icon = QIcon(os.path.dirname(__file__) + f'/{icon}.png')
        action = QAction(icon, menu, self.iface.mainWindow())
        action.triggered.connect(callback)
        self.toolbar.addAction(action)
        self.iface.addPluginToMenu(self.menu, action)
        return action


    # Add plugins actions
    def initGui(self):
        self.searchAction = self.addAction('Search OneAtlas', 'logo', self.showMySearch)

        self.layerAction = self.addAction('Display Imagery', 'layer', self.stream)
        self.disableLayerBtnByLayerSelection(self.iface.activeLayer())
        # self.layerAction.setEnabled(False)


    # Remove the toolbar
    def unload(self):
        for action in self.toolbar.actions():
            self.iface.removePluginMenu(self.menu, action)
        self.iface.mainWindow().removeToolBar(self.toolbar)


    # Init then show the search dialog
    def showMySearch(self):
        if self.mySearch is None:
            self.mySearch = MySearch(self.iface)
        self.mySearch.show()


    # Disable layer button is active layer isn't valid
    def disableLayerBtnByLayerSelection(self, layer):
        # Try to disconnect last layer selection detection
        # TODO this is really dirty...
        try:
            self.activeLayer.selectionChanged.disconnect(self.disableLayerBtnByFeatureSelection)
        except:
            pass
        # Disable layer button
        self.layerAction.setEnabled(False)
        # Check if current selected layer is a VectorLayer
        if isinstance(layer, QgsVectorLayer):
            self.activeLayer = layer
            # Connect the selection changed signal
            self.activeLayer.selectionChanged.connect(self.disableLayerBtnByFeatureSelection)
            self.disableLayerBtnByFeatureSelection()
            

    # Check if attributes 'service' exist in selected features
    def disableLayerBtnByFeatureSelection(self):
        self.layerAction.setEnabled(False)
        if self.activeLayer.selectedFeatureCount() == 1:
            self.selectedFeature = self.activeLayer.selectedFeatures()[0]
            self.layerAction.setEnabled(self.selectedFeature.fields().indexFromName('service') != -1)


    # Stream image
    def stream(self):

        goForStream = True

        # Avoid auth exception if you reopen the project and don't open the search
        if self.mySearch == None:
            self.mySearch = MySearch(self.iface)

        # Get selected feature of active layer
        service = self.selectedFeature['service']

        # Setup raster params
        isWcs = False
        if service == 'BaseMap':
            if self.mySearch.bmAuth is None:
                try:
                    self.mySearch.bmSetAuth()
                except:
                    return
            username = self.mySearch.bmUsernameInput.text()
            password = self.mySearch.bmPasswordInput.text()
            layers = self.mySearch.bmGetLayer(self.selectedFeature['wmts'])
            styles = 'default'
            tileMatrixSet = '4326'
            urlAttr = 'wmts'
        elif service == 'Data':
            if self.mySearch.dtHeaders is None:
                try:
                    self.mySearch.dtSetAuth()
                except:
                    return
            username = 'APIKEY'
            password = self.mySearch.dtApikeyInput.text()

            # Dialog for image choice (panchro/multi & wmts/wcs)
            self.msgBox = QMessageBox()
            self.msgBox.setWindowTitle(self.menu)

            if self.selectedFeature['processingLevel'] == 'ALBUM':
                self.iface.messageBar().pushMessage("Warning", "The feature can't be displayed (no WMTS for Archive features)", level=Qgis.Warning)
                goForStream = False
            else:
                protocolGroup = QGroupBox('Protocol')
                protocolGrid = QGridLayout()
                wmtsRadio = QRadioButton('WMTS')
                wcsRadio = QRadioButton('WCS')
                protocolGrid.addWidget(wmtsRadio, 0, 0)
                protocolGrid.addWidget(wcsRadio, 0, 1)
                protocolGroup.setLayout(protocolGrid)
                
                styleGroup = QGroupBox('Style')
                styleGrid = QGridLayout()
                multispectralRadio = QRadioButton('multispectral')
                panchromaticRadio = QRadioButton('panchromatic')
                pmsRadio = QRadioButton('pms')
                styleGrid.addWidget(multispectralRadio, 0, 0)
                styleGrid.addWidget(panchromaticRadio, 0, 1)
                styleGrid.addWidget(pmsRadio, 0, 2)
                styleGroup.setLayout(styleGrid)

                self.msgBox.layout().addWidget(protocolGroup, 0, 0)
                self.msgBox.layout().addWidget(styleGroup, 1, 0)

                wmtsRadio.setChecked(True)
                if type(self.selectedFeature['wcs_multispectral']) != str and type(self.selectedFeature['wcs_panchromatic']) != str and type(self.selectedFeature['wcs_pms']) != str:
                    protocolGroup.setEnabled(False)

                if type(self.selectedFeature['wmts_pms']) != str:
                    multispectralRadio.setEnabled(True)
                    panchromaticRadio.setEnabled(True)
                    pmsRadio.setEnabled(False)
                    multispectralRadio.setChecked(True)
                else:
                    multispectralRadio.setEnabled(True)
                    panchromaticRadio.setEnabled(True)
                    pmsRadio.setEnabled(True)
                    pmsRadio.setChecked(True)

                

                self.msgBox.setStandardButtons(QMessageBox.Abort | QMessageBox.Ok)
                reply = self.msgBox.exec_()
                if reply == QMessageBox.Abort:
                    return
                if wmtsRadio.isChecked():
                    urlAttr = 'wmts_'
                    layers = 'default'
                    styles = 'rgb'
                    tileMatrixSet = 'EPSG4326'
                else:
                    urlAttr = 'wcs_'
                    isWcs = True
                if multispectralRadio.isChecked():
                    urlAttr += 'multispectral'
                elif panchromaticRadio.isChecked():
                    urlAttr += 'panchromatic'
                else:
                    urlAttr += 'pms'
        else:
            self.error(f'Service "{service}" of the feature ocg_fid={self.selectedFeature.id()} isn\'t recognized\nIt should be "Basemap" or "Data"')
            return


        if goForStream:
            # Add a WMTS raster layer
            # Order of url parameters are important !
            # Why layers is required, maybe is an internal id for wmts gesture ?
            # What is styles ?
            try:
                url = self.selectedFeature[urlAttr]
                name = f'{service} {self.selectedFeature["id"]}'
                if isWcs:
                    rlayer = QgsRasterLayer(f'dpiMode=7&identifier=default&password={password}&url={url}&username={username}', name, 'wcs')
                else:
                    rlayer = QgsRasterLayer(f'crs=EPSG:4326&dpiMode=7&format=image/png&layers={layers}&password={password}&styles={styles}&tileMatrixSet={tileMatrixSet}&url={url}&username={username}', name, 'wms')
            except Exception as e:
                self.error(f'Error in protocol connection\n\n{str(e)}')
                return
            if rlayer.isValid() == False:
                self.error(f'Raster layer is invalid\n\n{rlayer.error()}')
                return

            QgsProject.instance().addMapLayer(rlayer)

    def error(self, msg):
        QMessageBox.critical(None, self.menu, msg)
