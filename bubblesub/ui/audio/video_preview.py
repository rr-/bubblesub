# bubblesub - ASS subtitle editor
# Copyright (C) 2018 Marcin Kurczewski
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import queue
import threading
import typing as T

import numpy as np
from PyQt5 import QtCore, QtGui, QtWidgets

from bubblesub.api import Api
from bubblesub.api.media.state import MediaState
from bubblesub.cache import load_cache, save_cache
from bubblesub.ui.audio.base import SLIDER_SIZE, BaseLocalAudioWidget
from bubblesub.util import sanitize_file_name

_CACHE_LOCK = threading.Lock()
_NOT_CACHED = object()
_BAND_Y_RESOLUTION = 30


class VideoBandWorker(QtCore.QObject):
    cache_updated = QtCore.pyqtSignal()

    def __init__(self, api: Api) -> None:
        super().__init__()
        self._api = api
        self._queue: queue.Queue = queue.Queue()
        self._running = False
        self._clearing = False
        self._anything_to_save = False
        self.cache: T.Dict[int, np.array] = {}

        api.media.state_changed.connect(self._on_media_state_change)
        api.media.video.parsed.connect(self._on_video_parse)

    def run(self) -> None:
        self._running = True
        while self._running:
            if self._clearing:
                continue
            frame_idx = self._queue.get()
            if frame_idx is None:
                break

            frame = (
                self._api.media.video.get_frame(
                    frame_idx, 1, _BAND_Y_RESOLUTION
                )
                .reshape(_BAND_Y_RESOLUTION, 3)
                .copy()
            )

            with _CACHE_LOCK:
                self.cache[frame_idx] = frame
            self.cache_updated.emit()
            self._anything_to_save = True

            self._queue.task_done()
            if self._queue.empty():
                self._save_to_cache()

    def stop(self) -> None:
        self._clear_queue()
        self._running = False

    def _on_media_state_change(self, state: MediaState) -> None:
        if state == MediaState.Unloaded:
            if self._anything_to_save:
                self._save_to_cache()
            with _CACHE_LOCK:
                self.cache = {}
            self.cache_updated.emit()
            self._clear_queue()
        elif state == MediaState.Loading:
            self._clear_queue()
            self._anything_to_save = False
            with _CACHE_LOCK:
                self.cache = self._load_from_cache()
            self.cache_updated.emit()

    def _on_video_parse(self) -> None:
        for frame_idx in range(len(self._api.media.video.timecodes)):
            with _CACHE_LOCK:
                if frame_idx not in self.cache:
                    self._queue.put(frame_idx)

    def _clear_queue(self) -> None:
        self._clearing = True
        while not self._queue.empty():
            try:
                self._queue.get(False)
            except queue.Empty:
                continue
            self._queue.task_done()
        self._clearing = False

    @property
    def _cache_name(self) -> T.Optional[str]:
        if not self._api.media.path:
            return None
        return sanitize_file_name(self._api.media.path) + "-video-band"

    def _load_from_cache(self) -> T.Dict[int, np.array]:
        cache = load_cache(self._cache_name) or {}
        return cache

    def _save_to_cache(self) -> None:
        if self._cache_name is not None:
            with _CACHE_LOCK:
                save_cache(self._cache_name, self.cache)


class VideoPreview(BaseLocalAudioWidget):
    def __init__(self, api: Api, parent: QtWidgets.QWidget = None) -> None:
        super().__init__(api, parent)
        self.setMinimumHeight(SLIDER_SIZE * 3)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Maximum
        )

        self._worker = VideoBandWorker(api)
        self._worker.cache_updated.connect(self._on_video_band_update)
        self._worker_thread = QtCore.QThread()
        self._worker.moveToThread(self._worker_thread)
        self._worker_thread.started.connect(self._worker.run)
        self._worker_thread.start()

        self._need_repaint = False
        self._pixels: np.array = np.zeros([0, 0, 3], dtype=np.uint8)

        timer = QtCore.QTimer(self)
        timer.setInterval(api.cfg.opt["audio"]["spectrogram_sync_interval"])
        timer.timeout.connect(self._repaint_if_needed)
        timer.start()

        api.media.state_changed.connect(self._on_media_state_change)
        api.media.audio.view_changed.connect(self._on_audio_view_change)
        api.media.video.parsed.connect(self._on_audio_view_change)

    def shutdown(self) -> None:
        self._worker.stop()

    def resizeEvent(self, _event: QtGui.QResizeEvent) -> None:
        self._pixels = np.zeros(
            [_BAND_Y_RESOLUTION, self.width(), 3], dtype=np.uint8
        )

    def paintEvent(self, _event: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter()

        painter.begin(self)
        self._draw_video_band(painter)
        self._draw_frame(painter, bottom_line=False)
        painter.end()

        self._need_repaint = False

    def _repaint_if_needed(self) -> None:
        if self._need_repaint:
            self.update()

    def _on_audio_view_change(self) -> None:
        self._need_repaint = True

    def _on_media_state_change(self, _state: MediaState) -> None:
        self.update()

    def _on_video_band_update(self) -> None:
        self._need_repaint = True

    def _draw_video_band(self, painter: QtGui.QPainter) -> None:
        pixels = self._pixels.transpose(1, 0, 2)
        prev_column = np.zeros([pixels.shape[1], 3], dtype=np.uint8)
        for x in range(pixels.shape[0]):
            frame_idx = self.frame_idx_from_x(x)
            column = self._worker.cache.get(frame_idx, _NOT_CACHED)
            if column is _NOT_CACHED:
                column = prev_column
            else:
                prev_column = column
            pixels[x] = column

        image = QtGui.QImage(
            self._pixels.data,
            self._pixels.shape[1],
            self._pixels.shape[0],
            self._pixels.strides[0],
            QtGui.QImage.Format_RGB888,
        )
        painter.save()
        painter.scale(
            1, painter.viewport().height() / (_BAND_Y_RESOLUTION - 1)
        )
        painter.drawPixmap(0, 0, QtGui.QPixmap.fromImage(image))
        painter.restore()
