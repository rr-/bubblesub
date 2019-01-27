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

import typing as T

from PyQt5 import QtCore, QtGui, QtWidgets

from bubblesub.api import Api
from bubblesub.cfg.hotkeys import HotkeyContext
from bubblesub.cfg.menu import MenuCommand, MenuContext, MenuSeparator, SubMenu
from bubblesub.ui.audio import Audio
from bubblesub.ui.console import Console
from bubblesub.ui.editor import Editor
from bubblesub.ui.hotkeys import HotkeyManager
from bubblesub.ui.menu import setup_cmd_menu
from bubblesub.ui.statusbar import StatusBar
from bubblesub.ui.subs_grid import SubtitlesGrid
from bubblesub.ui.video import Video


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, api: Api, console: Console) -> None:
        super().__init__()

        self._api = api
        self._update_title()

        api.gui.quit_requested.connect(self.close)
        api.gui.quit_confirmed.connect(self._store_splitters)
        api.gui.begin_update_requested.connect(
            lambda: self.setUpdatesEnabled(False)
        )
        api.gui.end_update_requested.connect(
            lambda: self.setUpdatesEnabled(True)
        )
        api.subs.loaded.connect(self._update_title)
        api.cmd.commands_loaded.connect(self._setup_menu)

        self.video = Video(api, self)
        self.audio = Audio(api, self)
        self.editor = Editor(api, self)
        self.subs_grid = SubtitlesGrid(api, self)
        self.status_bar = StatusBar(api, self)
        self.console = console

        self.editor_splitter = self._build_splitter(
            [(4, self.audio), (1, self.editor)], orientation=QtCore.Qt.Vertical
        )

        self.top_bar = self._build_splitter(
            [(1, self.video), (1, self.editor_splitter)],
            orientation=QtCore.Qt.Horizontal,
        )

        self.console_splitter = self._build_splitter(
            [(2, self.subs_grid), (1, console)],
            orientation=QtCore.Qt.Horizontal,
        )

        self.main_splitter = self._build_splitter(
            [(1, self.top_bar), (5, self.console_splitter)],
            orientation=QtCore.Qt.Vertical,
        )

        console.setParent(self.console_splitter)
        self.video.layout().setContentsMargins(0, 0, 2, 0)
        self.editor_splitter.setContentsMargins(2, 0, 0, 0)
        self.main_splitter.setContentsMargins(8, 8, 8, 8)

        self.setCentralWidget(self.main_splitter)
        self.setStatusBar(self.status_bar)

        self.subs_grid.setFocus()

        self.subs_grid.restore_grid_columns()
        self.apply_palette(api.cfg.opt["gui"]["current_palette"])
        self._restore_splitters()
        self._setup_menu()

        HotkeyManager(
            api,
            {
                HotkeyContext.Global: self,
                HotkeyContext.Spectrogram: self.audio,
                HotkeyContext.SubtitlesGrid: self.subs_grid,
            },
        )

    def changeEvent(self, _event: QtCore.QEvent) -> None:
        self._api.gui.get_color.cache_clear()

    def closeEvent(self, event: QtCore.QEvent) -> None:
        if self._api.gui.confirm_unsaved_changes():
            self._api.gui.quit_confirmed.emit()
            self.audio.shutdown()
            self.video.shutdown()
            event.accept()
        else:
            event.ignore()

    def apply_palette(self, palette_name: str) -> None:
        try:
            palette_def = self._api.cfg.opt["gui"]["palettes"][palette_name]
        except KeyError:
            raise ValueError(f'unknown palette: "{palette_name}"')

        self._api.cfg.opt["gui"]["current_palette"] = palette_name

        palette = QtGui.QPalette()
        for color_type in palette_def.keys():
            color = self._api.gui.get_color(color_type)
            if "+" in color_type:
                group_name, role_name = color_type.split("+")
            else:
                group_name = ""
                role_name = color_type
            target_group = getattr(QtGui.QPalette, group_name, None)
            target_role = getattr(QtGui.QPalette, role_name, None)
            if target_group is not None and target_role is not None:
                palette.setColor(target_group, target_role, color)
            elif target_role is not None:
                palette.setColor(target_role, color)
        self.setPalette(palette)

        self.update()

    def _build_splitter(
        self,
        widgets: T.List[T.Tuple[int, QtWidgets.QWidget]],
        orientation: int,
    ) -> QtWidgets.QSplitter:
        splitter = QtWidgets.QSplitter(self, orientation=orientation)
        for i, item in enumerate(widgets):
            stretch_factor, widget = item
            splitter.addWidget(widget)
            splitter.setStretchFactor(i, stretch_factor)
        return splitter

    def _setup_menu(self) -> None:
        setup_cmd_menu(
            self._api,
            self.menuBar(),
            self._api.cfg.menu[MenuContext.MainMenu]
            + [
                SubMenu(
                    "Pl&ugins",
                    [
                        MenuCommand("Reload plugins", "reload-cmds"),
                        MenuSeparator(),
                    ]
                    + self._api.cmd.get_plugin_menu_items(),
                )
            ],
            HotkeyContext.Global,
        )

    def _restore_splitters(self) -> None:
        def _load(widget: QtWidgets.QWidget, key: str) -> None:
            data = self._api.cfg.opt["gui"]["splitters"].get(key, None)
            if data:
                widget.restoreState(data)

        _load(self.top_bar, "top")
        _load(self.editor_splitter, "editor")
        _load(self.main_splitter, "main")
        _load(self.console_splitter, "console")

    def _store_splitters(self) -> None:
        self._api.cfg.opt["gui"]["splitters"] = {
            "top": bytes(self.top_bar.saveState()),
            "editor": bytes(self.editor_splitter.saveState()),
            "main": bytes(self.main_splitter.saveState()),
            "console": bytes(self.console_splitter.saveState()),
        }

    def _update_title(self) -> None:
        self.setWindowTitle(
            f"bubblesub - {self._api.subs.path}"
            if self._api.subs.path
            else "bubblesub"
        )
