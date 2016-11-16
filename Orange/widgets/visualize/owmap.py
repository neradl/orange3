import os
from itertools import chain, repeat, groupby
from collections import OrderedDict
from tempfile import mkstemp

import numpy as np

from AnyQt.QtCore import Qt, QUrl, pyqtSignal, pyqtSlot, QTimer, QT_VERSION_STR
from AnyQt.QtGui import QImage, QPainter, QPen, QBrush, QColor


from Orange.util import color_to_hex
from Orange.base import Learner
from Orange.data.util import scale
from Orange.data import Table, Domain, TimeVariable
from Orange.widgets import gui, widget, settings
from Orange.widgets.utils.itemmodels import VariableListModel
from Orange.widgets.utils.webview import WebviewWidget
from Orange.widgets.utils.colorpalette import ColorPaletteGenerator, ContinuousPaletteGenerator
from operator import itemgetter


if QT_VERSION_STR <= '5.3':
    raise RuntimeError('Map widget only works with Qt 5.3+')


class LeafletMap(WebviewWidget):
    selectionChanged = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent,
                         url=QUrl(self.toFileURL(
                             os.path.join(os.path.dirname(__file__), '_owmap', 'owmap.html'))),
                         debug=True,)
        self.jittering = 0
        self._owwidget = parent
        self._opacity = 255
        self._sizes = None
        self._selected_indices = None

        self.lat_attr = None
        self.lon_attr = None
        self.data = None
        self.model = None

        self._color_attr = None
        self._label_attr = None
        self._shape_attr = None
        self._size_attr = None
        self._legend_colors = []
        self._legend_shapes = []
        self._legend_sizes = []

        self._drawing_args = None
        self._image_token = None
        self._prev_map_pane_pos = None
        self._prev_origin = None
        self._overlay_image_path = mkstemp(prefix='orange-Map-', suffix='.png')[1]

    def __del__(self):
        os.remove(self._overlay_image_path)

    def set_data(self, data, lat_attr, lon_attr):
        self.data = data
        self.lat_attr = None
        self.lon_attr = None

        if data is None or not (len(data) and lat_attr and lon_attr):
            self.evalJS('clear_markers_js(); clear_markers_overlay_image();')
            return

        self.lat_attr = data.domain[lat_attr]
        self.lon_attr = data.domain[lon_attr]
        self.fit_to_bounds(False)

    def showEvent(self, *args):
        super().showEvent(*args)
        QTimer.singleShot(10, self.fit_to_bounds)

    @pyqtSlot()
    def fit_to_bounds(self, fly=True):
        lat_data = self.data.get_column_view(self.lat_attr)[0]
        lon_data = self.data.get_column_view(self.lon_attr)[0]
        north, south = np.nanmax(lat_data), np.nanmin(lat_data)
        east, west = np.nanmin(lon_data), np.nanmax(lon_data)
        self.evalJS('map.%sBounds([[%f, %f], [%f, %f]], {padding: [0, 0], maxZoom: 9})'
                    % ('flyTo' if fly else 'fit', south, west, north, east))

    @pyqtSlot(float, float, float, float)
    def selected_area(self, north, east, south, west):
        indices = np.array([])
        if north != south and east != west:
            lat = self.data.get_column_view(self.lat_attr)[0]
            lon = self.data.get_column_view(self.lon_attr)[0]
            indices = ((lat <= north) & (lat >= south) &
                       (lon <= east) & (lon >= west))
            if self._selected_indices is not None:
                indices |= self._selected_indices
            self._selected_indices = indices
        else:
            self._selected_indices = None
        self.selectionChanged.emit(indices.nonzero()[0].tolist())
        self.evalJS('redraw_markers_overlay_image();')

    def set_map_provider(self, provider):
        self.evalJS('set_map_provider("{}");'.format(provider))

    def set_clustering(self, cluster_points):
        self.evalJS('''
            window.cluster_points = {};
            set_cluster_points();
        '''.format(int(cluster_points)))

    def set_jittering(self, jittering):
        """ In percent, i.e. jittering=3 means 3% of screen height and width """
        self._jittering = jittering / 100
        self.evalJS('''
            window.jittering_percent = {};
            set_jittering();
            if (window.jittering_percent == 0)
                clear_jittering();
        '''.format(jittering))
        self.redraw_markers_overlay_image(new_image=True)

    def _legend_values(self, variable, values):
        strs = [variable.repr_val(val) for val in values]
        if any(len(val) > 10 for val in strs):
            if isinstance(variable, TimeVariable):
                strs = [s.replace(' ', '<br>') for s in strs]
            elif variable.is_continuous:
                strs = ['{:.4e}'.format(val) for val in values]
            elif variable.is_discrete:
                strs = [s if len(s) <= 12 else (s[:6] + '…' + s[-5:])
                        for s in strs]
        return strs

    def set_marker_color(self, attr, update=True):
        try:
            self._color_attr = variable = self.data.domain[attr]
        except Exception:
            self._color_attr = None
            self._legend_colors = []
        else:
            if variable.is_continuous:
                self._raw_color_values = values = self.data.get_column_view(variable)[0]
                self._scaled_color_values = scale(values)
                self._colorgen = ContinuousPaletteGenerator(*variable.colors)
                min = np.nanmin(values)
                self._legend_colors = (['c',
                                        self._legend_values(variable, [min, np.nanmax(values)]),
                                        [color_to_hex(i) for i in variable.colors if i]]
                                       if not np.isnan(min) else [])
            elif variable.is_discrete:
                _values = np.asarray(self.data.domain[attr].values)
                __values = self.data.get_column_view(variable)[0].astype(np.uint16)
                self._raw_color_values = _values[__values]  # The joke's on you
                self._scaled_color_values = __values
                self._colorgen = ColorPaletteGenerator(len(variable.colors), variable.colors)
                self._legend_colors = ['d',
                                       self._legend_values(variable, range(len(_values))),
                                       [color_to_hex(self._colorgen.getRGB(i))
                                        for i in range(len(_values))]]
        finally:
            if update:
                self.redraw_markers_overlay_image(new_image=True)

    def set_marker_label(self, attr, update=True):
        try:
            self._label_attr = variable = self.data.domain[attr]
        except Exception:
            self._label_attr = None
        else:
            if variable.is_continuous:
                self._label_values = self.data.get_column_view(variable)[0]
            elif variable.is_discrete:
                _values = np.asarray(self.data.domain[attr].values)
                __values = self.data.get_column_view(variable)[0].astype(np.uint16)
                self._label_values = _values[__values]  # The design had lead to poor code for ages
        finally:
            if update:
                self.redraw_markers_overlay_image(new_image=True)

    def set_marker_shape(self, attr, update=True):
        try:
            self._shape_attr = variable = self.data.domain[attr]
        except Exception:
            self._shape_attr = None
            self._legend_shapes = []
        else:
            assert variable.is_discrete
            _values = np.asarray(self.data.domain[attr].values)
            self._shape_values = __values = self.data.get_column_view(variable)[0].astype(np.uint16)
            self._raw_shape_values = _values[__values]
            self._legend_shapes = self._legend_values(variable, range(len(_values)))
        finally:
            if update:
                self.redraw_markers_overlay_image(new_image=True)

    def set_marker_size(self, attr, update=True):
        try:
            self._size_attr = variable = self.data.domain[attr]
        except Exception:
            self._size_attr = None
            self._legend_sizes = []
        else:
            assert variable.is_continuous
            self._raw_sizes = values = self.data.get_column_view(variable)[0]
            # Note, [5, 60] is also hardcoded in legend-size-indicator.svg
            self._sizes = scale(values, 5, 60).astype(np.uint8)
            min = np.nanmin(values)
            self._legend_sizes = self._legend_values(variable,
                                                     [min, np.nanmax(values)]) if not np.isnan(min) else []
        finally:
            if update:
                self.redraw_markers_overlay_image(new_image=True)

    def set_marker_size_coefficient(self, size):
        self._size_coef = size / 100
        self.evalJS('''set_marker_size_coefficient({});'''.format(size / 100))
        self.redraw_markers_overlay_image(new_image=True)

    def set_marker_opacity(self, opacity):
        self._opacity = 255 * opacity // 100
        self.evalJS('''set_marker_opacity({});'''.format(opacity / 100))
        self.redraw_markers_overlay_image(new_image=True)

    def set_model(self, model):
        self.model = model
        self.evalJS('clear_heatmap()' if model is None else 'reset_heatmap()')

    @pyqtSlot('QVariantList')
    def recompute_heatmap(self, points):
        if self.model is None or not self.data or not self.lat_attr or not self.lon_attr:
            return

        latlons = np.array(points)
        table = Table(Domain([self.lat_attr, self.lon_attr]), latlons)
        try:
            predictions = self.model(table)
        except Exception as e:
            self._owwidget.Error.model_error(e)
            return
        else:
            self._owwidget.Error.model_error.clear()
        predictions = scale(np.round(predictions, 7))  # Avoid small errors
        self.exposeObject('model_predictions', dict(data=predictions))
        self.evalJS('draw_heatmap()')

    def _update_js_markers(self, visible):
        self._visible = visible
        data = Table(Domain([self.lat_attr, self.lon_attr]), self.data)
        self.exposeObject('latlon_data', dict(data=data.X[visible]))
        self.exposeObject('selected_markers', dict(data=(self._selected_indices[visible]
                                                         if self._selected_indices is not None else 0)))
        if not self._color_attr:
            self.exposeObject('color_attr', dict())
        else:
            colors = [color_to_hex(rgb)
                      for rgb in self._colorgen.getRGB(self._scaled_color_values[visible])]
            self.exposeObject('color_attr',
                              dict(name=str(self._color_attr), values=colors,
                                   raw_values=self._raw_color_values[visible]))
        if not self._label_attr:
            self.exposeObject('label_attr', dict())
        else:
            self.exposeObject('label_attr',
                              dict(name=str(self._label_attr),
                                   values=self._label_values[visible]))
        if not self._shape_attr:
            self.exposeObject('shape_attr', dict())
        else:
            self.exposeObject('shape_attr',
                              dict(name=str(self._shape_attr),
                                   values=self._shape_values[visible],
                                   raw_values=self._raw_shape_values[visible]))
        if not self._size_attr:
            self.exposeObject('size_attr', dict())
        else:
            self.exposeObject('size_attr',
                              dict(name=str(self._size_attr),
                                   values=self._sizes[visible],
                                   raw_values=self._raw_sizes[visible]))
        self.evalJS('''
            window.latlon_data = latlon_data.data;
            window.selected_markers = selected_markers.data
            add_markers(latlon_data);
        ''')

    class Projection:
        """This should somewhat model Leaflet's Web Mercator (EPSG:3857).

        Reverse-engineered from L.Map.latlngToContainerPoint().
        """
        @staticmethod
        def latlon_to_easting_northing(lat, lon):
            R = 6378137
            MAX_LATITUDE = 85.0511287798
            DEG = np.pi / 180

            lat = np.clip(lat, -MAX_LATITUDE, MAX_LATITUDE)
            sin = np.sin(DEG * lat)
            x = R * DEG * lon
            y = R / 2 * np.log((1 + sin) / (1 - sin))
            return x, y

        @staticmethod
        def easting_northing_to_pixel(x, y, zoom_level, pixel_origin, map_pane_pos):
            R = 6378137
            PROJ_SCALE = .5 / (np.pi * R)

            zoom_scale = 256 * (2 ** zoom_level)
            x = (zoom_scale * (PROJ_SCALE * x + .5)).round() + (map_pane_pos[0] - pixel_origin[0])
            y = (zoom_scale * (-PROJ_SCALE * y + .5)).round() + (map_pane_pos[1] - pixel_origin[1])
            return x, y

    @pyqtSlot(float, float, float, float, int, int, float, 'QVariantList', 'QVariantList')
    def redraw_markers_overlay_image(self, *args, new_image=False):
        if (not args and not self._drawing_args or
                self.lat_attr is None or self.lon_attr is None):
            return

        if args:
            self._drawing_args = args
        north, east, south, west, width, height, zoom, origin, map_pane_pos = self._drawing_args

        lat = self.data.get_column_view(self.lat_attr)[0]
        lon = self.data.get_column_view(self.lon_attr)[0]
        visible = ((lat <= north) & (lat >= south) &
                   (lon <= east) & (lon >= west)).nonzero()[0]

        is_js_path = len(visible) <= 500

        self.evalJS('''
            window.legend_colors = %s;
            window.legend_shapes = %s;
            window.legend_sizes  = %s;
            legendControl.remove();
            legendControl.addTo(map);
        ''' % (self._legend_colors,
               self._legend_shapes if is_js_path else [],
               self._legend_sizes))

        if is_js_path:
            self.evalJS('clear_markers_overlay_image()')
            self._update_js_markers(visible)
            self._owwidget.disable_some_controls(False)
            return

        self.evalJS('clear_markers_js();')
        self._owwidget.disable_some_controls(True)

        np.random.shuffle(visible)

        selected = (self._selected_indices
                    if self._selected_indices is not None else
                    np.zeros(len(lat), dtype=bool))

        N_POINTS_PER_ITER = 1000
        cur = 0

        im = QImage(self._overlay_image_path)
        if im.isNull() or self._prev_origin != origin or new_image:
            im = QImage(width, height, QImage.Format_ARGB32)
            im.fill(Qt.transparent)
        else:
            dx, dy = self._prev_map_pane_pos - map_pane_pos
            im = im.copy(dx, dy, width, height)
        self._prev_map_pane_pos = np.array(map_pane_pos)
        self._prev_origin = origin

        painter = QPainter(im)
        painter.setRenderHint(QPainter.Antialiasing, True)
        self.evalJS('clear_markers_overlay_image(); markersImageLayer.setBounds(map.getBounds());0')

        self._image_token = image_token = np.random.random()

        n_iters = np.ceil(len(visible) / N_POINTS_PER_ITER)

        def add_points():
            nonlocal cur, image_token
            if image_token != self._image_token:
                return
            batch = visible[cur:cur + N_POINTS_PER_ITER]

            batch_lat = lat[batch]
            batch_lon = lon[batch]
            batch_selected = selected[batch]

            x, y = self.Projection.latlon_to_easting_northing(batch_lat, batch_lon)
            x, y = self.Projection.easting_northing_to_pixel(x, y, zoom, origin, map_pane_pos)

            if self._jittering:
                x += (np.random.random(len(x)) - .5) * (self._jittering * width)
                y += (np.random.random(len(x)) - .5) * (self._jittering * height)

            colors = (self._colorgen.getRGB(self._scaled_color_values[batch]).tolist()
                      if self._color_attr else
                      repeat((0xff, 0, 0)))
            sizes = self._sizes[batch] if self._size_attr else repeat(10)

            zipped = zip(x, y, batch_selected, colors, sizes)
            sortkey, penkey, brushkey = itemgetter(2, 3, 4), itemgetter(2), itemgetter(3, 4)
            for is_selected, points in groupby(sorted(zipped, key=sortkey),
                                               key=penkey):
                pensize, pencolor = (3, Qt.green) if is_selected else (.7, QColor(0, 0, 0, self._opacity))
                painter.setPen(QPen(QBrush(pencolor), pensize))

                for (color, size), points in groupby(points, key=brushkey):
                    color = tuple(color) + (self._opacity,)
                    painter.setBrush(QBrush(QColor(*color)))
                    size = size * self._size_coef + pensize
                    size2 = size / 2
                    for x, y, *_ in points:
                        painter.drawEllipse(x - size2, y - size2, size, size)

            im.save(self._overlay_image_path, 'PNG')
            self.evalJS('markersImageLayer.setUrl("{}#{}"); 0;'
                        .format(self._overlay_image_path, np.random.random()))

            cur += N_POINTS_PER_ITER
            if cur < len(visible):
                QTimer.singleShot(10, add_points)
                self._owwidget.progressBarAdvance(100 / n_iters, None)
            else:
                self._owwidget.progressBarFinished(None)

        self._owwidget.progressBarFinished(None)
        self._owwidget.progressBarInit(None)
        QTimer.singleShot(10, add_points)


class OWMap(widget.OWWidget):
    name = 'Map'
    description = 'Show data poits on a world map.'
    icon = "icons/Map.svg"

    inputs = [("Data", Table, "set_data"),
              ("Learner", Learner, "set_learner")]

    outputs = [("Selected Data", Table, widget.Default)]

    settingsHandler = settings.DomainContextHandler()

    want_main_area = True

    autocommit = settings.Setting(True)
    tile_provider = settings.Setting('Black and white')
    lat_attr = settings.ContextSetting('')
    lon_attr = settings.ContextSetting('')
    class_attr = settings.ContextSetting('')
    color_attr = settings.ContextSetting('')
    label_attr = settings.ContextSetting('')
    shape_attr = settings.ContextSetting('')
    size_attr = settings.ContextSetting('')
    opacity = settings.Setting(100)
    zoom = settings.Setting(100)
    jittering = settings.Setting(0)
    cluster_points = settings.Setting(False)

    TILE_PROVIDERS = OrderedDict((
        ('Black and white', 'OpenStreetMap.BlackAndWhite'),
        ('OpenStreetMap', 'OpenStreetMap.DE'),
        ('Topographic', 'OpenTopoMap'),
        ('Topographic 2', 'Thunderforest.OpenCycleMap'),
        ('Topographic 3', 'Thunderforest.Outdoors'),
        ('Satellite', 'Esri.WorldImagery'),
        ('Print', 'Stamen.TonerLite'),
        ('Light', 'CartoDB.Positron'),
        ('Dark', 'CartoDB.DarkMatter'),
        ('Railways', 'Thunderforest.Transport'),
        ('Watercolor', 'Stamen.Watercolor'),
    ))

    class Error(widget.OWWidget.Error):
        model_error = widget.Msg("Model couldn't predict: {}")
        missing_learner = widget.Msg('No input learner to model with')
        learner_error = widget.Msg("Learner couldn't model: {}")

    UserAdviceMessages = [
        widget.Message(
            'Select markers by holding <b><kbd>Shift</kbd></b> key and dragging '
            'a rectangle around them. Clear the selection by clicking anywhere.',
            'shift-selection')
    ]

    graph_name = "map"

    def __init__(self):
        super().__init__()
        self.map = map = LeafletMap(self)
        self.mainArea.layout().addWidget(map)
        self.selection = None
        self.data = None
        self.learner = None

        def selectionChanged(indices):
            self.selection = self.data[indices] if self.data is not None and indices else None
            self.commit()

        map.selectionChanged.connect(selectionChanged)

        def _set_map_provider():
            map.set_map_provider(self.TILE_PROVIDERS[self.tile_provider])

        box = gui.vBox(self.controlArea, 'Map')
        gui.comboBox(box, self, 'tile_provider',
                     orientation=Qt.Horizontal,
                     label='Map:',
                     items=tuple(self.TILE_PROVIDERS.keys()),
                     sendSelectedValue=True,
                     callback=_set_map_provider)

        self._latlon_model = VariableListModel(parent=self)
        self._class_model = VariableListModel(parent=self)
        self._color_model = VariableListModel(parent=self)
        self._shape_model = VariableListModel(parent=self)
        self._size_model = VariableListModel(parent=self)
        self._label_model = VariableListModel(parent=self)

        def _set_lat_long():
            self.map.set_data(self.data, self.lat_attr, self.lon_attr)
            self.train_model()

        self._combo_lat = combo = gui.comboBox(
            box, self, 'lat_attr', orientation=Qt.Horizontal,
            label='Latitude:', sendSelectedValue=True, callback=_set_lat_long)
        combo.setModel(self._latlon_model)
        self._combo_lon = combo = gui.comboBox(
            box, self, 'lon_attr', orientation=Qt.Horizontal,
            label='Longitude:', sendSelectedValue=True, callback=_set_lat_long)
        combo.setModel(self._latlon_model)

        def _set_class_attr():
            if not self.learner and self.class_attr != '(None)':
                self.Error.missing_learner()
            else:
                self.train_model()

        box = gui.vBox(self.controlArea, 'Heatmap')
        self._combo_class = combo = gui.comboBox(
            box, self, 'class_attr', orientation=Qt.Horizontal,
            label='Target:', sendSelectedValue=True, callback=_set_class_attr
        )
        combo.setModel(self._class_model)

        box = gui.vBox(self.controlArea, 'Points')
        self._combo_color = combo = gui.comboBox(
            box, self, 'color_attr',
            orientation=Qt.Horizontal,
            label='Color:',
            sendSelectedValue=True,
            callback=lambda: self.map.set_marker_color(self.color_attr))
        combo.setModel(self._color_model)
        self._combo_label = combo = gui.comboBox(
            box, self, 'label_attr',
            orientation=Qt.Horizontal,
            label='Label:',
            sendSelectedValue=True,
            callback=lambda: self.map.set_marker_label(self.label_attr))
        combo.setModel(self._label_model)
        self._combo_shape = combo = gui.comboBox(
            box, self, 'shape_attr',
            orientation=Qt.Horizontal,
            label='Shape:',
            sendSelectedValue=True,
            callback=lambda: self.map.set_marker_shape(self.shape_attr))
        combo.setModel(self._shape_model)
        self._combo_size = combo = gui.comboBox(
            box, self, 'size_attr',
            orientation=Qt.Horizontal,
            label='Size:',
            sendSelectedValue=True,
            callback=lambda: self.map.set_marker_size(self.size_attr))
        combo.setModel(self._size_model)

        def _set_opacity():
            map.set_marker_opacity(self.opacity)

        def _set_zoom():
            map.set_marker_size_coefficient(self.zoom)

        def _set_jittering():
            map.set_jittering(self.jittering)

        def _set_clustering():
            map.set_clustering(self.cluster_points)

        self._opacity_slider = gui.hSlider(
            box, self, 'opacity', None, 1, 100, 5,
            label='Opacity:', labelFormat=' %d%%',
            callback=_set_opacity)
        self._zoom_slider = gui.valueSlider(
            box, self, 'zoom', None, values=(20, 50, 100, 200, 500, 1000),
            label='Zoom:', labelFormat=' %d%%',
            callback=_set_zoom)
        self._jittering = gui.valueSlider(
            box, self, 'jittering', label='Jittering', values=(0, .5, 1, 2, 5),
            labelFormat=' %.1f%%', ticks=True,
            callback=_set_jittering)
        self._clustering_check = gui.checkBox(
            box, self, 'cluster_points', label='Cluster points',
            callback=_set_clustering)

        gui.rubber(self.controlArea)
        gui.auto_commit(self.controlArea, self, 'autocommit', 'Send Selection')

        QTimer.singleShot(0, _set_map_provider)
        QTimer.singleShot(0, _set_opacity)
        QTimer.singleShot(0, _set_zoom)
        QTimer.singleShot(0, _set_jittering)
        QTimer.singleShot(0, _set_clustering)

    autocommit = settings.Setting(True)

    def commit(self):
        self.send('Selected Data', self.selection)

    def set_data(self, data):
        self.data = data

        self.closeContext()

        if data is None:
            return self.clear()

        all_vars = list(chain(self.data.domain, self.data.domain.metas))
        continuous_vars = [var for var in all_vars if var.is_continuous]
        discrete_vars = [var for var in all_vars if var.is_discrete]
        primitive_vars = [var for var in all_vars if var.is_primitive]
        self._latlon_model.wrap(continuous_vars)
        self._class_model.wrap(['(None)'] + continuous_vars)
        self._color_model.wrap(['(Same color)'] + primitive_vars)
        self._shape_model.wrap(['(Same shape)'] + discrete_vars)
        self._size_model.wrap(['(Same size)'] + continuous_vars)
        self._label_model.wrap(['(No labels)'] + all_vars)

        def _find_lat_lon():
            STR_TRANSFORMS = (lambda x: x, str.capitalize, str.upper)
            lat_attr = next((attr
                             for attr in data.domain
                             if any(attr.name.startswith(transform(name))
                                    for name in ('latitude', 'lat')
                                    for transform in STR_TRANSFORMS)), None)
            lon_attr = next((attr
                             for attr in data.domain
                             if any(attr.name.startswith(transform(name))
                                    for name in ('longitude', 'long', 'lon')
                                    for transform in STR_TRANSFORMS)), None)
            return lat_attr, lon_attr

        lat, lon = _find_lat_lon()
        if lat and lon:
            self._combo_lat.setCurrentIndex(0 if lat is None else continuous_vars.index(lat))
            self._combo_lon.setCurrentIndex(0 if lat is None else continuous_vars.index(lon))
            self.lat_attr = lat.name
            self.lon_attr = lon.name
            self.map.set_data(self.data, lat, lon)
        self._combo_color.setCurrentIndex(0)
        self._combo_shape.setCurrentIndex(0)
        self._combo_size.setCurrentIndex(0)
        self._combo_label.setCurrentIndex(0)

        self.openContext(data)

        self.map.set_marker_color(self.color_attr, update=False)
        self.map.set_marker_label(self.label_attr, update=False)
        self.map.set_marker_shape(self.shape_attr, update=False)
        self.map.set_marker_size(self.size_attr, update=True)

    def handleNewSignals(self):
        super().handleNewSignals()
        self.train_model()

    def set_learner(self, learner):
        self.learner = learner

    def train_model(self):
        model = None
        self.Error.missing_learner.clear()
        if self.data is not None and self.learner is not None:
            if self.lat_attr and self.lon_attr and self.class_attr and self.class_attr != '(None)':
                domain = self.data.domain
                domain = Domain([domain[self.lat_attr], domain[self.lon_attr]],
                                [domain[self.class_attr]])  # I am retarded
                train = Table.from_table(domain, self.data)
                try:
                    model = self.learner(train)
                except Exception as e:
                    self.Error.learner_error(e)
                else:
                    self.Error.learner_error.clear()
        self.map.set_model(model)

    def disable_some_controls(self, disabled):
        self._combo_label.setDisabled(disabled)
        self._combo_shape.setDisabled(disabled)
        self._clustering_check.setDisabled(disabled)

    def clear(self):
        self.map.set_data(None, '', '')
        self._latlon_model.wrap([])
        self._class_model.wrap([])
        self._color_model.wrap(['(Same color)'])
        self._shape_model.wrap(['(Same shape)'])
        self._size_model.wrap(['(Same size)'])
        self._label_model.wrap(['(No labels)'])
        self.lat_attr = self.lon_attr = self.class_attr = self.color_attr = \
        self.label_attr = self.shape_attr = self.size_attr = ''
        self.train_model()


def test_main():
    from AnyQt.QtWidgets import QApplication
    a = QApplication([])

    ow = OWMap()
    ow.show()
    ow.raise_()
    data = Table('cov_all_netcom_oslo_trond-small.tab')
    ow.set_data(data)

    ow.handleNewSignals()

    class RandomLearner:
        def __call__(self, *args, **kwargs):
            return RandomModel()

    class RandomModel:
        def __call__(self, data):
            return np.random.random(len(data))

    QTimer.singleShot(10, lambda: ow.set_learner(RandomLearner()))

    a.exec()
    ow.saveSettings()

if __name__ == "__main__":
    test_main()
