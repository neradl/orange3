var _IS_WEBENGINE = /QtWebEngine/.test(navigator.userAgent);

if (!_IS_WEBENGINE) {
    // On WebKit, the styling applied in CSS does not produce sufficient border
    var stylesheet = document.styleSheets[document.styleSheets.length - 1];
    stylesheet.insertRule(
        '.orange-marker img {\
            -webkit-filter: drop-shadow(0px 0px 1px black);\
            filter: drop-shadow(0px 0px 1px black);\
        }', stylesheet.rules.length);
}


var _DEFAULT_COLOR = 'red',
    _DEFAULT_SIZE = 12,
    _DEFAULT_SHAPE = 0,
    _MAX_SIZE = 120,
    // On WebKit, this lengthy 1px transparent PNG is the only thing that works
    _TRANSPARENT_IMAGE = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQI12NgYGBgAAAABQABXvMqOgAAAABJRU5ErkJggg==';

var tileLayer = L.tileLayer.provider('OpenStreetMap.BlackAndWhite');

var markers = [],
    latlon_data = [],
    markersLayer = L.featureGroup(),
    jittering_offsets = [],
    cluster_points = false;

/* Objects passed from Python:
       {name: attr.name,
        values: coded values used in presentation,
        raw_values: raw values for show in popup if different from values}
 */
var color_attr = {},
    shape_attr = {},
    label_attr = {},
    size_attr = {};


var map = L.map('map', {
    preferCanvas: true,
    layers: [tileLayer, markersLayer],
    worldCopyJump: true
});
map.fitWorld();
map.on('zoom', reposition_markers);

L.easyButton('<img src="target.png" class="custom-button">', function () {
    __self.fit_to_bounds();
}).addTo(map);

map.on('mousedown', function (e) {
    if (map.dragging.enabled()) return;

    var ev = new MouseEvent('mousedown', $.extend({}, e.originalEvent, {shiftKey: true}));
    map.boxZoom._onMouseDown(ev);
    return false;
});
var zoomButton = L.easyButton({
    states: [{
        stateName: 'default',
        icon: '<img src="zoom.png" class="custom-button">',
        title: 'Zoom to rectangle selection',
        onClick: function (control) {
            control.state('active');
            control.button.classList.add('custom-button-toggle');
            $('.leaflet-container').css('cursor','crosshair');
            map.dragging.disable();
        }
    }, {
        stateName: 'active',
        icon: '<img src="zoom.png" class="custom-button">',
        title: 'Cancel zooming',
        onClick: function (control) {
            control.state('default');
            control.button.classList.remove('custom-button-toggle');
            $('.leaflet-container').css('cursor','');
            map.dragging.enable();
        }
    }]
}).addTo(map);

var heatmapLayer = L.imageOverlay('data:', [[0, 0], [0, 0]], {attribution: 'Orange – Data Mining Fruitful &amp; Fun'}).addTo(map);
var markersImageLayer = L.imageOverlay(_TRANSPARENT_IMAGE, [[0, 0], [0, 0]]).addTo(map);

var BoxSelect = L.Map.BoxZoom.extend({
    _onMouseUp: function (e) {
        // Just prevent fitting the new box bounds, super for everything else
        var old_fitBounds = this._map.fitBounds;
        this._map.fitBounds = function() { return this; };

        L.Map.BoxZoom.prototype._onMouseUp.call(this, e);

        this._map.fitBounds = old_fitBounds;
    }
});
// Disable internal boxZoom handler and override it with our BoxSelect handler
map.boxZoom.disable();
map.addHandler('boxZoom', BoxSelect);
map.on("boxzoomend", function(e) {
    if (!map.dragging.enabled()) {
        zoomButton.options.states[1].onClick(zoomButton);
        map.flyToBounds(e.boxZoomBounds, {padding: [-.1, -.1]});
    } else {
        var box = e.boxZoomBounds;
        for (var i = 0; i < markers.length; i++) {
            var marker = markers[i];
            marker._our_selected = false;
            if (box.contains(marker.getLatLng())) {
                marker.setSelected(true);
            }
        }
        __self.selected_area(box.getNorth(), box.getEast(), box.getSouth(), box.getWest())
    }
});
map.on('click', function() {
    for (var i = 0; i < markers.length; i++) {
        var marker = markers[i];
        marker.setSelected(false);
    }
    __self.selected_area(0, 0, 0, 0);
});


function popup_callback(marker) {
    var i = marker._orange_id,
        str = L.Util.template('\
<b>Latitude:</b> {lat}<br>\
<b>Longitude:</b> {lon}<br>\
<b></b>', {
        lat: latlon_data[i][0].toFixed(6),
        lon: latlon_data[i][1].toFixed(6)
    });
    var attrs = [color_attr, shape_attr, label_attr, size_attr];
    for (var a in attrs) {
        var attr = attrs[a];
        if (!$.isEmptyObject(attr))
            str += L.Util.template('<b>{name}:</b> {value}<br>', {
                name: attr.name,
                value: (attr.raw_values || attr.values)[i] || 0
            });
    }
    return str
}


L.OurMarker = L.Marker.extend({
    // We need this method to fire after marker._icon is constructed.
    // Without this method, we would have to use marker.setIcon() in
    // _update_markers(), but that would be much slower.
    // The need for this method is obvious when toggling marker clustering.
    update: function () {
        if (this._icon)
            _update_marker_icon(this);
        return L.Marker.prototype.update.call(this);
    },
    setSelected: function(selected) {
        this._our_selected = !!selected;
        var method = this._icon && (selected ? 'add' : 'remove');
        method && this._icon.classList[method]('orange-marker-selected');
    },
    isSelected: function() {
        return this._our_selected;
    }
});
L.ourMarker = function (latlng, options) {
    return new L.OurMarker(latlng, options);
};

function add_markers(latlon_data) {
    console.info('adding map markers: ' + latlon_data.length);

    clear_markers_js();

    var markerOptions = {
        icon: L.divIcon({
            className: 'orange-marker',
            html: '<img/><span></span>'
        }),
        riseOnHover: true
    };
    var markerEvents = {
        mouseover: function(ev) {
            var marker = ev.target;
            if (marker._firing_close_popup)
                clearTimeout(marker._firing_close_popup);
            marker.openPopup();
        },
        mouseout: function(ev) {
            var marker = ev.target;
            marker._firing_close_popup = setTimeout(function() {
                marker._firing_close_popup = 0;
                marker.closePopup();
            }, 500);
        }
    };

    for (var i = 0; i < latlon_data.length; ++i) {
        var marker = L.ourMarker(latlon_data[i], markerOptions);
        if (selected_markers[i])
            marker.setSelected(true);
        marker._orange_id = i;  // Used in popup_callback() and the like
        marker.bindPopup(popup_callback);
        marker.on(markerEvents);
        markers.push(marker);
    }
    _update_markers();
    set_cluster_points();
    set_jittering();
}


var _icons_canvas_ctx = document.getElementById('icons_canvas').getContext('2d'),
    _icons_cache = {};

function _construct_icon(shape, color) {
    shape = Math.min(7, shape);
    var cached;
    if (cached = _icons_cache[[shape, color]])
        return cached;

    var ctx = _icons_canvas_ctx,
        size = _MAX_SIZE,
        stroke = size / 20,
        size = size - 2 * stroke;

    ctx.clearRect(0, 0, size + 2 * stroke, size + 2 * stroke);
    ctx.canvas.width = ctx.canvas.height = size + 2 * stroke;
    ctx.fillStyle = color;
    ctx.strokeStyle = "black";
    ctx.lineWidth = stroke;

    // Strokes for shapes added with CSS via filter:drop-shadow()
    switch (shape) {
        case 0:
            // Circle
            ctx.beginPath();
            ctx.arc(size / 2 + stroke, size / 2 + stroke, size / 2, 0, Math.PI * 2, true);
            ctx.fill();
            ctx.closePath();
            break;

        case 1:
            // Cross
            ctx.rect(stroke, stroke, size, size);
            ctx.clip();
            ctx.beginPath();
            ctx.moveTo(stroke, stroke);
            ctx.lineTo(size + stroke, size + stroke);
            ctx.moveTo(size + stroke, stroke);
            ctx.lineTo(stroke, size + stroke);
            ctx.save();
            ctx.lineWidth = size / 3;
            ctx.strokeStyle = color;
            ctx.stroke();
            ctx.restore();
            ctx.closePath();
            break;

        case 2:
            // Triangle
            ctx.beginPath();
            ctx.moveTo(stroke + size / 2, stroke);
            ctx.lineTo(stroke + size, stroke + size);
            ctx.lineTo(stroke, stroke + size);
            ctx.lineTo(stroke + size / 2, stroke);
            ctx.closePath();
            ctx.fill();
            break;

        case 3:
            // Plus
            ctx.beginPath();
            ctx.moveTo(size / 2 + stroke, stroke);
            ctx.lineTo(size / 2 + stroke, size + stroke);
            ctx.moveTo(stroke, size / 2 + stroke);
            ctx.lineTo(size + stroke, size / 2 + stroke);
            ctx.closePath();
            ctx.save();
            ctx.lineWidth = size / 3;
            ctx.strokeStyle = color;
            ctx.stroke();
            ctx.restore();
            break;

        case 4:
            // Diamond
            ctx.beginPath();
            ctx.save();
            ctx.rotate(Math.PI / 4);
            size /= Math.SQRT2;
            ctx.rect(2 * stroke + size / 2, - size / 2, size, size);
            ctx.restore();
            ctx.closePath();
            ctx.fill();
            break;

        case 5:
            // Square
            ctx.beginPath();
            ctx.rect(stroke, stroke, size, size);
            ctx.closePath();
            ctx.fill();
            break;

        case 6:
            // Inverse triangle
            ctx.beginPath();
            ctx.moveTo(stroke, stroke);
            ctx.lineTo(stroke + size, stroke);
            ctx.lineTo(stroke + size / 2, stroke + size);
            ctx.lineTo(stroke, stroke);
            ctx.closePath();
            ctx.fill();
            break;

        case 7:
            // Bowtie
            ctx.beginPath();
            ctx.moveTo(stroke, stroke);
            ctx.lineTo(stroke + size / 2, stroke + size / 2);
            ctx.lineTo(stroke, stroke + size);
            ctx.lineTo(stroke, stroke);
            ctx.moveTo(stroke + size, stroke);
            ctx.lineTo(stroke + size / 2, stroke + size / 2);
            ctx.lineTo(stroke + size, stroke + size);
            ctx.lineTo(stroke + size, stroke);
            ctx.closePath();
            ctx.fill();
            break;

        case 8:
            // Flank
            size += 2 * stroke;
            ctx.beginPath();
            ctx.save();
            ctx.translate(size / 2 + stroke, size / 2 + stroke);
            for (var i=0; i<4; ++i) {
                ctx.moveTo(0, 0);
                ctx.lineTo(0, -size / 2 + size / 9 + 2 * stroke);
                ctx.lineTo(size / 2 - 2 * stroke, -size / 2 + size / 9 + 2 * stroke);
                ctx.rotate(-Math.PI / 2);
            }
            ctx.strokeStyle = color;
            ctx.lineWidth = size / 6;
            ctx.stroke();
            ctx.restore();
            ctx.closePath();
            break;

        default:
            console.error('invalid shape: ' + shape);
            return '';
    }
    return _icons_cache[[shape, color]] = ctx.canvas.toDataURL();
}


function clear_markers_js() {
    markersLayer.clearLayers();
    markers.length = 0;
}

function reposition_markers() {
    if (!markers.length)
        return;
    if (jittering_offsets.length) {
        if (markers.length != jittering_offsets.length || markers.length != latlon_data.length)
            return console.error('markers.length != jittering_offsets.length || markers.length != latlon_data.length ???');
        var data = latlon_data,
            div = map.getContainer(),
            w = div.clientWidth,
            h = div.clientHeight;
        for (var i = 0; i < markers.length; ++i) {
            var offset = jittering_offsets[i],
                old_px = map.latLngToContainerPoint(data[i]),
                new_pt = map.containerPointToLatLng([old_px.x + h * offset[0],
                                                     old_px.y + w * offset[1]]);
            markers[i].setLatLng(new_pt);
        }
    }
}

var jittering_percent = 0;

function set_jittering() {
    percent = jittering_percent / 100;
    jittering_offsets.length = 0;
    if (percent == 0)
        return;
    for (var i = 0; i < latlon_data.length; ++i) {
        jittering_offsets.push([(Math.random() - .5) * percent,
                                (Math.random() - .5) * percent]);
    }
    reposition_markers();
}

function clear_jittering() {
    jittering_offsets.length = 0;
    for (var i = 0; i < markers.length; ++i) {
        markers[i].setLatLng(latlon_data[i]);
    }
}


function set_map_provider(provider) {
    var new_provider = L.tileLayer.provider(provider).addTo(map);
    tileLayer.removeFrom(map);
    tileLayer = new_provider;
}


function _update_markers() {
    var shapes = shape_attr.values,
        colors = color_attr.values,
        labels = label_attr.values,
        sizes = size_attr.values;
    for (var i=0; i<markers.length; ++i) {
        var marker = markers[i],
            size = (sizes && sizes[i] || _DEFAULT_SIZE) * _size_coefficient;
        marker._our_icon_uri = _construct_icon(
            shapes && shapes[i] || _DEFAULT_SHAPE,
            colors && colors[i] || _DEFAULT_COLOR);
        marker.options.icon.options.popupAnchor = [0, -size / 2];
        marker._our_icon_size = size + 'px';
        marker._our_icon_margin = -size / 2 + 'px';
        marker._our_icon_label = labels && ('' + labels[i]) || '';
    }
    for (var i=0; i<markers.length; ++i)
        if (markers[i]._icon)
            _update_marker_icon(markers[i]);
}

function _update_marker_icon(marker) {
    var icon = marker._icon,
        img = icon.firstChild;
    img.src = marker._our_icon_uri;
    icon.style.width = icon.style.height =
        img.style.width = img.style.height = marker._our_icon_size;
    icon.style.marginTop = icon.style.marginLeft = marker._our_icon_margin;
    icon.lastChild.innerHTML = marker._our_icon_label;
    if (marker.isSelected())
        icon.classList.add('orange-marker-selected');
}


var _opacity_stylesheet = document.styleSheets[document.styleSheets.length - 1];
var _opacity_stylesheet_rule = _opacity_stylesheet.insertRule(
    '.orange-marker { opacity: .8; }',
    _opacity_stylesheet.rules.length);

function set_marker_opacity(opacity) {
    _opacity_stylesheet.deleteRule(_opacity_stylesheet_rule);
    _opacity_stylesheet.insertRule(
        '.orange-marker { opacity: ' + opacity + '; }',
        _opacity_stylesheet_rule);
}


var _size_coefficient = 1;

function set_marker_size_coefficient(coeff) {
    window._size_coefficient = coeff;
    _update_markers();
}


function set_cluster_points() {
    var old_markersLayer = markersLayer;
    if (cluster_points) {
        markersLayer = L.markerClusterGroup();
        markersLayer.addLayers(markers);
    } else {
        markersLayer = L.featureGroup(markers);
    }
    old_markersLayer.removeFrom(map);
    markersLayer.addTo(map);
}


function reset_heatmap() {
    var points = [],
        div = map.getContainer(),
        b = map.getPixelBounds(),
        top_offset = b.min.y < 0 ? -b.min.y : 0,
        b = map.getPixelWorldBounds(),
        height = Math.min(div.clientHeight - top_offset, b.max.y),
        width = div.clientWidth,
        dlat = height / _HEATMAP_GRID_SIZE,
        dlon = width / _HEATMAP_GRID_SIZE;
    // Project pixel coordinates into latlng pairs
    for (var i=0; i < _HEATMAP_GRID_SIZE; ++i) {
        var y = top_offset + i*dlat + dlat/2; // +dlat/2 ==> centers of squares
        for (var j=0; j < _HEATMAP_GRID_SIZE; ++j) {
            var latlon = map.containerPointToLatLng([j*dlon + dlon/2, y]);
            points.push([latlon.lat, latlon.lng]);
        }
    }
    __self.recompute_heatmap(points);
}

var _heatmap_canvas_ctx = document.getElementById('heatmap_canvas').getContext('2d'),
    _HEATMAP_GRID_SIZE = _heatmap_canvas_ctx.canvas.width;
_heatmap_canvas_ctx.fillStyle = 'red';
_heatmap_canvas_ctx.fillRect(0, 0, _HEATMAP_GRID_SIZE, _HEATMAP_GRID_SIZE);
var _canvas_imageData = _heatmap_canvas_ctx.getImageData(0, 0, _HEATMAP_GRID_SIZE, _HEATMAP_GRID_SIZE),
    _heatmap_pixels = _canvas_imageData.data;

// Workaround, results in better image upscaing interpolation,
// but only in WebEngine (Chromium). Old Apple WebKit does just as pretty but
// much faster job with translate3d(), which this pref affects. See also:
// https://github.com/Leaflet/Leaflet/pull/4869
L.Browser.ie3d = _IS_WEBENGINE;

function draw_heatmap() {
    var values = model_predictions.data;
    for (var y = 0; y < _HEATMAP_GRID_SIZE; ++y) {
        for (var x = 0; x < _HEATMAP_GRID_SIZE; ++x) {
            var i = y * _HEATMAP_GRID_SIZE + x;
            _heatmap_pixels[i * 4 + 3] = (values[i] * 200);  // alpha
        }
    }
    _heatmap_canvas_ctx.putImageData(_canvas_imageData, 0, 0);
    heatmapLayer
        .setUrl(_heatmap_canvas_ctx.canvas.toDataURL())
        .setBounds(map.getBounds());
}

function clear_heatmap() {
    heatmapLayer.setUrl(_TRANSPARENT_IMAGE);
}

function clear_markers_overlay_image() {
    markersImageLayer.setUrl(_TRANSPARENT_IMAGE);
}


function redraw_markers_overlay_image() {
    var bbox = map.getBounds(),
        size = map.getSize(),
        origin = map.getPixelOrigin(),
        pane_pos = map.getPane('mapPane')._leaflet_pos;
    __self.redraw_markers_overlay_image(
        bbox.getNorth(), bbox.getEast(), bbox.getSouth(), bbox.getWest(),
        size.x, size.y,
        map.getZoom(), [origin.x, origin.y], [pane_pos.x, pane_pos.y]);
}


$(document).ready(function() {
    setTimeout(function() { map.on('moveend', reset_heatmap); }, 100);
    setTimeout(function() { map.on('moveend', redraw_markers_overlay_image); }, 100);
});


var legendControl = L.control({position: 'topright'}),
    legend_colors = [],
    legend_shapes = [],
    legend_sizes = [];
legendControl.onAdd = function () {
    if (legend_colors.length +
        legend_shapes.length +
        legend_sizes.length == 0)
        return L.DomUtil.create('span');

    var div = L.DomUtil.create('div', 'legend');

    if (legend_colors.length) {
        var box = L.DomUtil.create('div', 'legend-box', div);
        box.innerHTML += '<h3>Color</h3><hr/>';
        if (legend_colors[0] == 'c') {
            box.innerHTML += L.Util.template(
                '<table class="colors">' +  // I'm sorry
                '<tr><td rowspan="2" style="width:2em; background:linear-gradient({colors})"></td><td> {minval}</td></tr>' +
                '<tr><td> {maxval}</td></tr>' +
                '</table>', {
                    minval: legend_colors[1][0],
                    maxval: legend_colors[1][1],
                    colors: legend_colors[2].join(',')
                });
        } else {
            var str = '';
            for (var i=0; i<legend_colors[1].length; ++i)
                str += L.Util.template(
                    '<div><div class="legend-icon" style="background:{color}">&nbsp;</div> {value}</div>', {
                        color: legend_colors[2][i],
                        value: legend_colors[1][i]});
            box.innerHTML += str;
        }
    }

    if (legend_shapes.length) {
        var box = L.DomUtil.create('div', 'legend-box', div);
        var str = '';
        for (var i=0; i<legend_shapes.length; ++i)
            str += L.Util.template(
                '<div><img class="legend-icon" style="vertical-align:middle" src="{shape}"/> {value}</div>', {
                    shape: _construct_icon(i, '#555'),
                    value: legend_shapes[i]});
        box.innerHTML = '<h3>Shape</h3><hr/>' + str;
    }

    if (legend_sizes.length) {
        var box = L.DomUtil.create('div', 'legend-box', div);
        box.innerHTML += '<h3>Size</h3><hr/>' + L.Util.template(
            '<table class="sizes">' +  // I'm sorry
            '<tr><td rowspan="2"><img src="legend-sizes-indicator.svg"></td><td> {minval}</td></tr>' +
            '<tr><td> {maxval}</td></tr>' +
            '</table>', {
                minval: legend_sizes[0],
                maxval: legend_sizes[1],
            });
    }

    return div;
};
