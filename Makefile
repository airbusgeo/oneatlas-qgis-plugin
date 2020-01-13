PLUGINNAME = OneAtlas
PLUGINS = $(HOME)/.local/share/QGIS/QGIS3/profiles/default/python/plugins/$(PLUGINNAME)
PY_FILES = __init__.py oneAtlas.py mySearch.py
EXTRAS = metadata.txt logo.png search.png layer.png
UI_FILES = mySearch.ui

deploy: 
	mkdir -p $(PLUGINS)
	cp -vf $(PY_FILES) $(PLUGINS)
	cp -vf $(UI_FILES) $(PLUGINS)
	cp -vf $(EXTRAS) $(PLUGINS)
