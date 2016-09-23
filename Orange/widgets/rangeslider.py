from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
# from PyQt4 import QtCore
# from PyQt4.QtGui import *
# from PyQt4.QtCore import *


def _INVALID(*args):
    raise RuntimeError


class RangeSlider(QSlider):
    valuesChanged = pyqtSignal(int, int)
    slidersMoved = pyqtSignal(int, int)
    sliderPressed = pyqtSignal(int)
    sliderReleased = pyqtSignal(int)

    # Prevent some QAbstractSlider defaults
    value = setValue = sliderPosition = setSliderPosition = \
        sliderMoved = valueChanged = _INVALID

    def __init__(self, *args, **kwargs):
        minimum = kwargs.get('minimum', 0)
        maximum = kwargs.get('maximum', 0)
        self.__min_value = self.__min_position = kwargs.pop('minimumValue', minimum)
        self.__max_value = self.__max_position = kwargs.pop('maximumValue', maximum)
        self.__min_position = kwargs.pop('minimumPosition', self.__min_position)
        self.__max_position = kwargs.pop('maximumPosition', self.__max_position)

        kwargs.setdefault('orientation', Qt.Horizontal)
        kwargs.setdefault('tickPosition', self.TicksBelow)

        super().__init__(*args, **kwargs)

        self.__pressed_control = QStyle.SC_None
        self.__hovered_control = QStyle.SC_None
        self.__active_slider = -1
        self.__click_offset = 0

    def paintEvent(self, event):
        # based on
        # https://github.com/qt/qtbase/blob/f40dbe0d0b54ce83d2168e82905cf4f75059a841/src/widgets/widgets/qslider.cpp#L315
        # https://github.com/enthought/traitsui/blob/master/traitsui/qt4/extra/range_slider.py
        painter = QStylePainter(self)
        minpos = self.__min_position
        maxpos = self.__max_position

        # Draw the groove
        opt = QStyleOptionSlider()
        self.initStyleOption(opt)
        # Draw empty grove
        opt.sliderPosition = opt.minimum
        opt.subControls = QStyle.SC_SliderGroove
        if self.tickPosition() != self.NoTicks:
            opt.subControls |= QStyle.SC_SliderTickmarks
        painter.drawComplexControl(QStyle.CC_Slider, opt)
        # Draw the highlighted part on top
        # Qt4.8 and Qt5.3 draw the highlighted groove in a weird way because they
        # transpose opt.rect. Qt5.7 works fine.
        if QT_VERSION_STR >= '5.7.0':
            opt.subControls = QStyle.SC_SliderGroove
            opt.sliderPosition = opt.maximum
            if self.orientation() == Qt.Horizontal:
                _w = opt.rect.width() / opt.maximum
                x = round(_w * minpos)
                w = round(_w * (maxpos - minpos))
                opt.rect = QRect(x, 0, w, opt.rect.height())
            else:
                _h = opt.rect.height() / opt.maximum
                y = round(_h * minpos)
                h = round(_h * (maxpos - minpos))
                opt.rect = QRect(0, y, opt.rect.width(), h)
            painter.drawComplexControl(QStyle.CC_Slider, opt)

        # Draw the handles
        for i, position in enumerate((minpos, maxpos)):
            opt = QStyleOptionSlider()
            self.initStyleOption(opt)
            opt.subControls = QStyle.SC_SliderHandle

            if self.__pressed_control and (self.__active_slider == i or
                                           self.__active_slider < 0):
                opt.activeSubControls = self.__pressed_control
                opt.state |= QStyle.State_Sunken
            else:
                opt.activeSubControls = self.__hovered_control

            opt.sliderPosition = position
            opt.sliderValue = position
            painter.drawComplexControl(QStyle.CC_Slider, opt)

    def mouseReleaseEvent(self, event):
        self.__pressed_control = QStyle.SC_None
        if not self.hasTracking():
            self.setValues(self.__min_position, self.__max_position)

    def mousePressEvent(self, event):
        if not event.button():
            event.ignore()
            return

        event.accept()
        style = self.style()

        opt = QStyleOptionSlider()
        self.initStyleOption(opt)

        self.__active_slider = -1

        for i, value in enumerate((self.__min_position, self.__max_position)):
            opt.sliderPosition = value
            hit = style.hitTestComplexControl(style.CC_Slider, opt, event.pos(), self)
            if hit == style.SC_SliderHandle:
                self.__active_slider = i
                self.__pressed_control = hit

                self.triggerAction(self.SliderMove)
                self.setRepeatAction(self.SliderNoAction)
                self.setSliderDown(True)
                break
        else:
            # If the user clicks the groove between the handles, the whole
            # interval is moved
            self.__pressed_control = QStyle.SC_SliderGroove
            self.__click_offset = self.__pixelPosToRangeValue(self.__pick(event.pos()))
            self.triggerAction(self.SliderMove)
            self.setRepeatAction(self.SliderNoAction)

    def mouseMoveEvent(self, event):
        if self.__pressed_control not in (QStyle.SC_SliderGroove,
                                          QStyle.SC_SliderHandle):
            event.ignore()
            return

        event.accept()
        opt = QStyleOptionSlider()
        self.initStyleOption(opt)
        pos = self.__pixelPosToRangeValue(self.__pick(event.pos()))

        if self.__active_slider < 0:
            offset = pos - self.__click_offset
            self.__max_position = min(self.__max_position + offset, self.maximum())
            self.__min_position = max(self.__min_position + offset, self.minimum())
            self.__click_offset = pos
        else:
            if self.__active_slider == 0:
                self.__min_position = max(self.minimum(), pos)
                self.__max_position = min(self.maximum(), max(self.__max_position, self.__min_position + 1))
            else:
                self.__max_position = min(self.maximum(), pos)
                self.__min_position = max(self.minimum(), min(self.__min_position, self.__max_position - 1))

        self.update()
        self.slidersMoved.emit(self.__min_position, self.__max_position)
        # This is different from QAbstractSlider, which sets the value
        # insider triggerAction() which would be called here instead.
        # But I don't want to override that as well, so simply:
        if self.hasTracking():
            self.setValues(self.__min_position, self.__max_position)

    def __pick(self, pt):
        return pt.x() if self.orientation() == Qt.Horizontal else pt.y()

    def __pixelPosToRangeValue(self, pos):
        opt = QStyleOptionSlider()
        self.initStyleOption(opt)
        style = self.style()

        groove = style.subControlRect(QStyle.CC_Slider, opt, QStyle.SC_SliderGroove, self)
        handle = style.subControlRect(QStyle.CC_Slider, opt, QStyle.SC_SliderHandle, self)

        if self.orientation() == Qt.Horizontal:
            slider_length = handle.width()
            slider_min = groove.x()
            slider_max = groove.right() - slider_length + 1
        else:
            slider_length = handle.height()
            slider_min = groove.y()
            slider_max = groove.bottom() - slider_length + 1

        return style.sliderValueFromPosition(
            self.minimum(), self.maximum(), pos - slider_min,
            slider_max - slider_min, opt.upsideDown)

    def values(self):
        return self.__min_value, self.__max_value

    def setValues(self, minValue, maxValue):
        self.__min_position = self.__min_value = max(minValue, self.minimum())
        self.__max_position = self.__max_value = min(maxValue, self.maximum())
        self.valuesChanged.emit(self.__min_value, self.__max_value)
        self.update()

    def minimumValue(self):
        return self.__min_value

    def setMinimumValue(self, minimumValue):
        self.__min_value = minimumValue
        self.update()

    def maximumValue(self):
        return self.__max_value

    def setMaximumValue(self, maximumValue):
        self.__max_value = maximumValue
        self.update()

    def minimumPosition(self):
        return self.__min_position

    def setMinimumPosition(self, minPosition):
        self.__min_position = minPosition
        self.slidersMoved(self.__min_position, self.__max_position)
        self.update()

    def maximumPosition(self):
        return self.__max_position

    def setMaximumPosition(self, maxPosition):
        self.__max_position = maxPosition
        self.slidersMoved(self.__min_position, self.__max_position)
        self.update()


if __name__ == "__main__":
    app = QApplication([])
    win = QDialog()
    hbox = QHBoxLayout(win)
    win.setLayout(hbox)
    label = QLabel('Slider:', win)
    slider = RangeSlider(win,
                         orientation=Qt.Horizontal,
                         minimum=0,
                         maximum=100,
                         tickInterval=5,
                         minimumValue=10,
                         maximumValue=90,
                         slidersMoved=print,
                         )
    hbox.addWidget(label)
    hbox.addWidget(slider)
    win.show()
    app.exec()
