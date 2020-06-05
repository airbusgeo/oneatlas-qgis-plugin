import os
import requests
import datetime
from xml.dom import minidom

import sys


from qgis.PyQt.uic import loadUiType
from qgis.PyQt.QtWidgets import QAction, QDialog, QDialogButtonBox, QMessageBox
from qgis.PyQt.QtGui import QIcon, QColor

from qgis.core import (
    QgsVectorLayer,
    QgsWkbTypes,
    QgsVectorFileWriter,
    QgsProject,
    QgsFeature,
    QgsGeometry,
    QgsRectangle,
    QgsField
)

from PyQt5 import QtNetwork
from PyQt5.QtCore import Qt, QVariant, QSettings

FORM_CLASS, _ = loadUiType(os.path.join(os.path.dirname(__file__), 'mySearch.ui'))

# Access class through python console
# my = qgis.utils.plugins['OneAtlas'].mySearch

# Set geometry from bbox of an other geometry
# feature.setGeometry(QgsGeometry.fromWkt(geometry.boundingBox().asWktPolygon()))

# Notif
# iface.messageBar().pushMessage('Error', 'Hello error', level=Qgis.Info, duration=0)

# bm = basemap
# dt = data

WINDOW_TITLE = 'OneAtlas'

# Table attributs
BASE_ATTR = {
    'service': 'string',
    'id': 'string',
    'constellation': 'string',
    'incidenceAngle': 'double',
    'cloudCover': 'double'}
BM_ATTR = dict(BASE_ATTR)
BM_ATTR.update({
    'insertionDate': 'string',
    'wmts': 'string'})
DT_ATTR = dict(BASE_ATTR)
DT_ATTR.update({
    'service' : 'string',
    'id' : 'string',
    'acquisitionIdentifier' : 'string',
    'parentIdentifier' : 'string',
    'sourceIdentifier' : 'string',
    'constellation' : 'string',
    'acquisitionDate': 'string',
    'cloudCover' :'double',
    'incidenceAngle' : 'double',
    'snowCover': 'double',
    'processingLevel' : 'string',
    'wmts_panchromatic': 'string', 
    'wmts_multispectral': 'string',
    'wmts_pms': 'string',
    'wcs_panchromatic': 'string',
    'wcs_multispectral': 'string',
    'wcs_pms': 'string'})

def joinFieldsAttributes(ATTR):
    array = []
    for key, value in ATTR.items():
        array.append(f'field={key}:{value}')
    return '&'.join(array)

BM_FIELDS = joinFieldsAttributes(BM_ATTR)
DT_FIELDS = joinFieldsAttributes(DT_ATTR)

FIELDS = {'BaseMap': BM_FIELDS, 'Data': DT_FIELDS}

class MySearch(QDialog, FORM_CLASS):

    def __init__(self, iface):
        super(MySearch, self).__init__(iface.mainWindow())
        self.iface = iface

        #--- PROXIES
        self.initSession()

        #--- UI
        self.setupUi(self)
        self.setWindowTitle(WINDOW_TITLE)
        
        # Connect polygon and draw buttons
        # MAYBE change inputLine for TextLine and find a way to print properly on 2 lines
        self.polygonBtn.clicked.connect(self.fillPolygonInput)
        # Connect function who diable polygon button
        self.iface.currentLayerChanged.connect(self.disablePolygonBtnByLayerSelection)
        self.disablePolygonBtnByLayerSelection(self.iface.activeLayer())

        self.drawBtn.clicked.connect(self.startDraw)

        # Set UI default tab and connect tab change function
        self.tab.currentChanged.connect(self.onTabChange)
        self.tab.setCurrentIndex(0)

        # Add icon and connect search button
        # FIXME resources, for now just add icon on some buttons programatically
        self.searchBtn.setIcon(QIcon(os.path.dirname(__file__) + f'/search.png'))
        self.searchBtn.clicked.connect(self.search)
        # Connect signals who can disable search button
        self.dtSpotCheck.stateChanged.connect(self.disableSearchBtn)
        self.dtPleiadesCheck.stateChanged.connect(self.disableSearchBtn)
        self.dtPublicCheck.stateChanged.connect(self.disableSearchBtn)
        self.dtPrivateCheck.stateChanged.connect(self.disableSearchBtn)
        self.polygonInput.textChanged.connect(self.disableSearchBtn)
        self.disableSearchBtn()

        #--- AUTH
        # Set auth variables and connect inputs to reset auth functions
        self.bmAuthReset()
        self.bmUsernameInput.textChanged.connect(self.bmAuthReset)
        self.bmPasswordInput.textChanged.connect(self.bmAuthReset)
        self.dtAuthReset()
        self.dtApikeyInput.textChanged.connect(self.dtAuthReset)


    #--- PROXIES --------------------------------------------------------------#

    def initSession(self):
        # Initialize the session for all requests
        self.session = requests.Session()

        settings = QSettings()
        if settings.value('proxy/proxyEnabled', '') == 'true':
            http = settings.value('proxy/proxyHost', '')
            port = settings.value('proxy/proxyPort', '')
            print(f'{http}:{port}')
            if http != '' and port != '':
                self.session.proxies = {'http': f'{http}:{port}', 'https':f'{http}:{port}'}
        else:
            print('No Proxy')


    #--- UI -------------------------------------------------------------------#

    # Show an error dialog
    def error(self, msg):
        QMessageBox.critical(None, WINDOW_TITLE, msg)


    # Show an error in UI
    def showErrorLbl(self, msg=''):
        self.errorLbl.setText(msg)


    # Disable layer button is active layer isn't valid
    def disablePolygonBtnByLayerSelection(self, layer):
        # Try to disconnect last layer selection detection
        # TODO this is really dirty...
        try:
            self.activeLayer.selectionChanged.disconnect(self.disablePolygonBtnByLayerSelection)
        except:
            pass
        # Disable polygon button
        self.polygonBtn.setEnabled(False)
        self.polygonBtn.setToolTip(f'Select 1 polygon in a vector layer')
        # Check if current selected layer is a VectorLayer
        if isinstance(layer, QgsVectorLayer):
            self.activeLayer = layer
            # Connect the selection changed signal
            self.activeLayer.selectionChanged.connect(self.disablePolygonBtnByFeatureSelection)
            self.disablePolygonBtnByFeatureSelection()
            

    # Check if attributes 'service' exist in selected features
    def disablePolygonBtnByFeatureSelection(self):
        self.polygonBtn.setEnabled(False)
        if self.activeLayer.selectedFeatureCount() == 1:
            self.selectedFeature = self.activeLayer.selectedFeatures()[0]
            self.polygonBtn.setEnabled(True)
            self.polygonBtn.setToolTip('')
        

    # Initialise the qgis feature tool to draw a new AOI
    def startDraw(self):
        # Create and add the new layer
        layer = QgsVectorLayer('Polygon?crs=epsg:4326', providerLib='memory')
        layer.renderer().symbol().setColor(QColor.fromRgb(160,82,45))
        layer.setName(f'search aoi')
        QgsProject.instance().addMapLayer(layer)

        # Use the add feature tool
        self.iface.setActiveLayer(layer)
        # Function called when the feature is added to the layer
        def featureAdded():
            # Disconnect from the signal
            layer.featureAdded.disconnect()
            # Save changes and end edit mode
            layer.commitChanges()
            # Select the feature then fill the input
            feature = layer.selectAll()
            self.fillPolygonInput()
        # Connect the layer to the signal featureAdded
        layer.featureAdded.connect(featureAdded)
        layer.startEditing()
        self.iface.actionAddFeature().trigger()


    # Fill the polygon input with a selected polygon (wkt)
    def fillPolygonInput(self):
        # Get the geometry of the single selected feature then fill the input with string polygon
        # Need to format to uppercase for search params
        polygon = self.selectedFeature.geometry().asWkt().upper()
        print(polygon)
        self.polygonInput.setText(polygon)


    # Hide or Show and change text of search button
    def onTabChange(self, i):
        # Configuration tab : hide
        if i == 0:
            self.searchBtn.hide()
        # Else show with the right text
        else:
            if i == 1:
                self.searchBtn.setText('Basemap search')
            else:
                self.searchBtn.setText('Data search')
            self.searchBtn.show()


    # Disable search button if there is problem in parameters
    def disableSearchBtn(self):
        errors = []
        if self.polygonInput.text() == '':
            errors.append('Fill the <b>Polygon</b> input')
        # MAYBE catch bad format polygon (space between POLYGON and parenthese, missing parentese and more...)
        # POLYGON \((\((-?\d+(\.\d+)? -?\d+(\.\d+)?)(, -?\d+(\.\d+)? -?\d+(\.\d+)?)*\))+\)
        elif QgsGeometry.fromWkt(self.polygonInput.text()).isGeosValid() == False:
            errors.append('<b>Polygon</b> is invalid (check for crossing lines or double points)')
        if not self.dtSpotCheck.isChecked() and not self.dtPleiadesCheck.isChecked():
            errors.append('Check at least one <b>Sensor</b>')
        if not self.dtPublicCheck.isChecked() and not self.dtPrivateCheck.isChecked():
            errors.append('Check at least one <b>Workspace</b>')
        error = '<br>'.join(errors)
        self.searchBtn.setEnabled(error == '')
        self.showErrorLbl(error)
        

    #--- AUTH -----------------------------------------------------------------#

    def bmAuthReset(self):
        self.bmAuth = None

    def bmSetAuth(self):
        print('Set Basemap auth...')

        # Set auth for the first time and test it
        if self.bmAuth is None:
            self.bmAuth = requests.auth.HTTPBasicAuth(self.bmUsernameInput.text(), self.bmPasswordInput.text())
            r = self.session.get('https://view.geoapi-airbusds.com/api/v1/me', auth=self.bmAuth)

            # Exception bad authentication
            if r.status_code != 200:
                self.bmAuthReset()
                self.error('Basemap authentication error')
                raise
            
    def dtAuthReset(self):
        self.dtHeaders = None
        self.dtWorkspaceId = None

    def dtSetAuth(self):
        print('Set Data auth...')

        # Set header for the first time and test it
        if self.dtHeaders is None or self.dtWorkspaceId is None:
            r = self.session.post('https://authenticate.foundation.api.oneatlas.airbus.com/auth/realms/IDP/protocol/openid-connect/token',
                            headers={'Content-Type':'application/x-www-form-urlencoded'},
                            data={'apikey':self.dtApikeyInput.text(), 'grant_type':'api_key', 'client_id':'IDP'})

            # Exception bad authentication
            if r.status_code != 200:
                self.dtAuthReset()
                self.error('Data authentication error')
                raise

            # MAYBE decode x64 to print rights or some other usefull info ?
            self.dtHeaders = {'Content-Type':'application/json', 'Authorization':f'Bearer {r.json()["access_token"]}'}

            r = self.session.get('https://data.api.oneatlas.airbus.com/api/v1/me', headers=self.dtHeaders)

            # Exception workspace error
            if r.status_code != 200:
                self.dtAuthReset()
                self.error('Data get workspace id error')
                raise

            self.dtWorkspaceId = r.json()['contract']['workspaceId']


    #--- API CALL -------------------------------------------------------------#

    # Return the current datetime format without microseconds
    def now(self):
        return datetime.datetime.now().replace(microsecond=0).isoformat()

    # Get a properties of api feature if exist, else return None
    def getPropertie(self, rFeature, name):
        try:
            return rFeature['properties'][name]
        except:
            return None

    # Search images with api
    def search(self):
        try:
            # Current service
            service = self.tab.tabText(self.tab.currentIndex())

            # Params
            params = {'geometry': self.polygonInput.text()}

            # Set auth and add params according to service
            if service == 'BaseMap':
                # ! Auth
                self.bmSetAuth()
                
                # Set request attributes
                url = 'https://view.geoapi-airbusds.com/api/v1/images'
                auth = self.bmAuth
                headers = None

                # Update params
                params.update({
                    'size': self.maxResultsInput.value(), 
                    'insertdtstart': '1970-01-01T00:00:00',
                    'insertdtend': self.now()})
                
                # Dates
                if self.bmFromCheck.isChecked():
                    params['insertdtstart'] = self.bmFromInput.dateTime().toString(Qt.ISODate)
                if self.bmToCheck.isChecked():
                    params['insertdtend'] = self.bmToInput.dateTime().toString(Qt.ISODate)

            else:
                # ! Auth
                self.dtSetAuth()

                url = 'https://search.foundation.api.oneatlas.airbus.com/api/v1/opensearch'
                auth = None
                headers = self.dtHeaders

                # Constellations (at least one)
                constellations = []
                if self.dtSpotCheck.isChecked():
                    constellations.append('SPOT')
                if self.dtPleiadesCheck.isChecked():
                    constellations.append('PHR')
                
                # Dates
                # MAYBE remove hours from dates
                dateFrom, dateTo = '1970-01-01T00:00:00', self.now()
                if self.dtFromCheck.isChecked():
                    dateFrom = self.dtFromInput.dateTime().toString(Qt.ISODate)
                if self.dtToCheck.isChecked():
                    dateTo = self.dtToInput.dateTime().toString(Qt.ISODate)

                # Angles
                angleMin, angleMax = 0, 30
                if self.dtAngleMinCheck.isChecked():
                    angleMin = self.dtAngleMinInput.value()
                if self.dtAngleMaxCheck.isChecked():
                    angleMax = self.dtAngleMaxInput.value()

                # Covers (directlly update params)
                if self.dtCloudCheck.isChecked():
                    params['cloudCover'] = f'[0,{self.dtCloudInput.value()}]'
                if self.dtSnowCheck.isChecked():
                    params['snowCover'] = f'[0,{self.dtSnowInput.value()}]'

                # Workspaces (at leat one)
                workspaces = []
                if self.dtPublicCheck.isChecked():
                    workspaces.append('0e33eb50-3404-48ad-b835-b0b4b72a5625')
                if self.dtPrivateCheck.isChecked():
                    workspaces.append(self.dtWorkspaceId)

                # Update all params with right format
                params.update({
                    'itemsPerPage': self.maxResultsInput.value(),
                    'constellation': ','.join(constellations),
                    'acquisitionDate': f'[{dateFrom},{dateTo}]',
                    'incidenceAngle': f'[{angleMin},{angleMax}]',
                    'workspace': ','.join(workspaces)})

            # Finally do the api call
            t = datetime.datetime.now()
            print(f'START {service} search')
            r = self.session.get(url, auth=auth, headers=headers, params=params)
            print(f'Result : {r}')
            rSearch = r.json()

            # Exception request error
            if r.status_code != 200:
                self.error(f'{service} search error {r.status_code}\n{rSearch["message"]}')
                print(f'Result (Json) : {rSearch}')
                return

            print ('Total Results : '+ str(rSearch['totalResults']))

            # Create the search result layer with fields according to current service
            layer = QgsVectorLayer(f'Polygon?crs=epsg:4326&index=yes&{FIELDS[service]}', providerLib='memory', baseName=f'{service} search results')

            # Extract features
            features = []
            self.errorFeatures = []
            for rFeature in rSearch['features']:
                # Add a feature of the bbox on the new layer
                feature = QgsFeature(layer.fields())            
                # Try to get each attributes
                feature['service'] = service
                feature['constellation'] = self.getPropertie(rFeature, 'constellation')
                feature['incidenceAngle'] = self.getPropertie(rFeature, 'incidenceAngle')
                feature['cloudCover'] = self.getPropertie(rFeature, 'cloudCover')
                if service == 'BaseMap':
                    feature['id'] = rFeature['id']
                    feature['insertionDate'] = self.getPropertie(rFeature, 'insertionDate')
                    feature['wmts'] = self.getPropertie(rFeature, 'wmts')
                    # Bbox
                    fBbox = rFeature['properties']['bbox']
                    rectangle = QgsRectangle(fBbox[0], fBbox[1], fBbox[2], fBbox[3])
                else:
                    feature['id'] = self.getPropertie(rFeature, 'id')
                    feature['acquisitionIdentifier'] = self.getPropertie(rFeature, 'acquisitionIdentifier')
                    feature['sourceIdentifier'] = self.getPropertie(rFeature, 'sourceIdentifier')
                    feature['parentIdentifier'] = self.getPropertie(rFeature, 'parentIdentifier')
                    feature['processingLevel'] = self.getPropertie(rFeature, 'processingLevel')
                    feature['acquisitionDate'] = self.getPropertie(rFeature, 'acquisitionDate')
                    feature['snowCover'] = self.getPropertie(rFeature, 'snowCover')
                    try:

                        # Warmup / Archive images (processingLevel=ALBUM) don't have WMTS or WCS links
                        if self.getPropertie(rFeature, 'processingLevel') != 'ALBUM':
                            # More than one record, it's a list
                            if type(rFeature['_links']['imagesWmts']) is list:
                                for json in rFeature['_links']['imagesWmts']:
                                    feature[f'wmts_{json["name"]}'] = json['href']
                            # Only one record, it's a dict
                            else:
                                json =rFeature['_links']['imagesWmts']
                                # Is the key "name" exist in the <dict> ?
                                if "name" in rFeature["_links"]["imagesWmts"]:
                                    feature[ f'wmts_{json["name"]}' ] = json['href']
                                else:
                                    feature['wmts_pms'] = json['href']

                            # More than one record, it's a list
                            if type(rFeature['_links']['imagesWcs']) is list:
                                for json in rFeature['_links']['imagesWcs']:
                                    if 'buffer' in rFeature['rights']:
                                        # Is the key "name" exist in the <dict> ?
                                        if "name" in rFeature["_links"]["imagesWcs"]:
                                            feature[f'wcs_{json["name"]}'] = json['href']
                                        else:
                                            feature['wcs_pms'] = json['href']
                                    else:
                                        # Is the key "name" exist in the <dict> ?
                                        if "name" in rFeature["_links"]["imagesWcs"]:
                                            feature[f'wcs_{json["name"]}'] = None
                                        else:
                                            feature['wcs_pms'] = None
                            # Only one record, it's a dict
                            else:
                                json =rFeature['_links']['imagesWcs']
                                if 'buffer' in rFeature['rights']:
                                    # Is the key "name" exist in the <dict> ?
                                    if "name" in rFeature["_links"]["imagesWcs"]:
                                        feature[f'wcs_{json["name"]}'] = json['href']
                                    else:
                                        feature['wcs_pms'] = json['href']
                                else:
                                    # Is the key "name" exist in the <dict> ?
                                    if "name" in rFeature["_links"]["imagesWcs"]:
                                        feature[f'wcs_{json["name"]}'] = None
                                    else:
                                        feature['wcs_pms'] = None

                    except Exception as e:
                        print(f'ERROR * eF = qgis.utils.plugins["OneAtlas"].mySearch.errorFeatures[{len(self.errorFeatures)}]')
                        print(str(e))

                        exc_type, exc_obj, exc_tb = sys.exc_info()
                        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
                        print(exc_type, fname, exc_tb.tb_lineno)

                        self.errorFeatures.append(rFeature)
                        continue
                    # Bbox
                    coordinates = rFeature['geometry']['coordinates'][0]
                    rectangle = QgsRectangle(coordinates[0][0], coordinates[0][1], coordinates[2][0], coordinates[2][1])
                # Add geometry from rectangle
                feature.setGeometry(QgsGeometry.fromWkt(rectangle.asWktPolygon()))
                # Add feature to list
                features.append(feature)

            # Total
            if service == 'BaseMap':
                # Note : rSearch['totalResults'] is maybe the number of total element in bbox ?
                #   and numberOfElements is the true total result
                total = rSearch['numberOfElements']
                color = QColor.fromRgb(0,250,0)
            else:
                total = rSearch['totalResults']
                color = QColor.fromRgb(0,250,250)

            if len(self.errorFeatures) > 0:
                total -= len(self.errorFeatures)
                print(f'* {len(self.errorFeatures)} error feature')

            # Notification for number of total results
            msgBox = QMessageBox()
            msgBox.setWindowTitle(WINDOW_TITLE)
            msgBox.setText(f'There are {total} results')
            if total > len(features):
                msgBox.setIcon(QMessageBox.Warning)
                msgBox.setInformativeText(f'The maximum is configured to {self.maxResultsInput.value()}\nPlease refine your criteria or your AOI')
                msgBox.setStandardButtons(QMessageBox.Retry | QMessageBox.Ignore)
                msgBox.setDefaultButton(QMessageBox.Retry)
            else:
                msgBox.setIcon(QMessageBox.Information)
                msgBox.setStandardButtons(QMessageBox.Retry | QMessageBox.Ok)
                msgBox.setDefaultButton(QMessageBox.Ok)
            msgBox.button(QMessageBox.Retry).setText('Refine')
            msgBox.button(QMessageBox.Retry).setIcon(QIcon(os.path.dirname(__file__) + f'/search.png'))

            reply = msgBox.exec_()
            if reply == QMessageBox.Retry or len(features) == 0:
                return

            # Add result feature to the new layer
            (res, outFeats) = layer.dataProvider().addFeatures(features)

            # Change layer syle programmatically
            # Note : if we styling before save and add layer, we avoid to update legend style
            #   => self.iface.layerTreeView().refreshLayerSymbology(vlayer.id())
            symbol = layer.renderer().symbol()
            symbol.setOpacity(0.2)
            symbol.setColor(color)

            QgsProject.instance().addMapLayer(layer)
            # And refresh view
            layer.triggerRepaint()
            self.close()
        except:
            return

    # Get the layers parameters extracted from GetCapabilities
    def bmGetLayer(self, wmtsUrl):
        r = self.session.get(wmtsUrl, auth=self.bmAuth, params={'service': 'WMTS', 'request': 'GetCapabilities'})
        # Convert response to XML
        xml = r.content.decode('utf-8')
        doc = minidom.parseString(xml)
        # Find the layers id
        layerDoc = doc.getElementsByTagName('Layer')[0]
        layers = layerDoc.getElementsByTagName('ows:Identifier')[0].firstChild.data
        return layers
