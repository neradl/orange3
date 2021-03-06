import numpy as np

from Orange.data import Table, Domain, ContinuousVariable, DiscreteVariable
from Orange.widgets.visualize.owmap import OWMap
from Orange.widgets.tests.base import WidgetTest
from Orange.regression.knn import KNNRegressionLearner


class TestOWMap(WidgetTest):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.data = Table(Domain([ContinuousVariable('latitude'),
                                 ContinuousVariable('longitude'),
                                 DiscreteVariable('foo', list(map(str, range(5))))]),
                         np.c_[np.random.random((20, 2)) * 10,
                               np.random.randint(5, size=20)])

    def setUp(self):
        super().setUp()
        self.widget = self.create_widget(OWMap)

    def test_inputs(self):
        self.widget.set_data(self.data)
        self.widget.set_learner(KNNRegressionLearner())
        self.widget.handleNewSignals()
        self.assertEqual(self.widget.map.lat_attr, self.data.domain[0])

    def test_projection(self):
        lat = np.r_[-89, 0, 89]
        lon = np.r_[-180, 0, 180]
        easting, northing = self.widget.map.Projection.latlon_to_easting_northing(lat, lon)
        x, y = self.widget.map.Projection.easting_northing_to_pixel(
            easting, northing, 0, [0, 0], [0, 0])
        np.testing.assert_equal(x, [0, 128, 256])
        np.testing.assert_equal(y, [256, 128, 0])

    def test_coverage(self):
        # Due to async nature of these calls, these tests just cover
        self.widget.set_data(self.data)
        self.widget.map.fit_to_bounds()
        self.widget.map.selected_area(90, 180, -90, -180)
        self.widget.map.set_map_provider(next(iter(self.widget.TILE_PROVIDERS.values())))
        self.widget.map.set_clustering(True)
        self.widget.map.set_jittering(5)
        self.widget.map.set_marker_color('latitude')
        self.widget.map.set_marker_label('latitude')
        self.widget.map.set_marker_shape('foo')
        self.widget.map.set_marker_size('latitude')
        self.widget.map.set_marker_size_coefficient(50)
        self.widget.map.set_marker_opacity(20)
        self.widget.map.recompute_heatmap(np.random.random((30, 30)))
        self.widget.map._update_js_markers([0, 1, 2, 3])
        self.widget.clear()
