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

"""Commands related to audio and audio selection."""

import argparse
import typing as T

import bubblesub.api
from bubblesub.api.cmd import BaseCommand
from bubblesub.api.cmd import CommandUnavailable
from bubblesub.cmd.common import EventSelection
from bubblesub.cmd.common import RelativePts


class AudioScrollCommand(BaseCommand):
    names = ['audio-scroll', 'spectrogram-scroll']
    help_text = (
        'Scrolls the spectrogram horizontally by its width\'s percentage.'
    )

    async def run(self) -> None:
        distance = int(self.args.delta * self.api.media.audio.view_size)
        self.api.media.audio.move_view(distance)

    @staticmethod
    def _decorate_parser(
            api: bubblesub.api.Api,
            parser: argparse.ArgumentParser
    ) -> None:
        parser.add_argument(
            '-d', '--delta',
            help='factor to shift the view by',
            type=float,
            required=True
        )


class AudioZoomCommand(BaseCommand):
    names = ['audio-zoom', 'spectrogram-zoom']
    help_text = 'Zooms the spectrogram in or out by the specified factor.'

    async def run(self) -> None:
        mouse_x = 0.5
        cur_factor = self.api.media.audio.view_size / self.api.media.audio.size
        new_factor = cur_factor * self.args.delta
        self.api.media.audio.zoom_view(new_factor, mouse_x)

    @staticmethod
    def _decorate_parser(
            api: bubblesub.api.Api,
            parser: argparse.ArgumentParser
    ) -> None:
        parser.add_argument(
            '-d', '--delta',
            help='factor to zoom the view by',
            type=float,
            required=True
        )


class AudioShiftSelectionCommand(BaseCommand):
    names = [
        'audio-shift-sel',
        'audio-shift-selection',
        'spectrogram-shift-sel',
        'spectrogram-shift-selection'
    ]
    help_text = 'Shfits the spectrogram selection.'

    async def run(self) -> None:
        with self.api.undo.capture():
            start = self.api.media.audio.selection_start
            end = self.api.media.audio.selection_end

            if self.args.method in {'start', 'both'}:
                start = await self.args.delta.apply(
                    start, align_to_near_frame=not self.args.no_align
                )

            if self.args.method in {'end', 'both'}:
                end = await self.args.delta.apply(
                    end, align_to_near_frame=not self.args.no_align
                )

            self.api.media.audio.select(start, end)

    @staticmethod
    def _decorate_parser(
            api: bubblesub.api.Api,
            parser: argparse.ArgumentParser
    ) -> None:
        parser.add_argument(
            '-d', '--delta',
            help='amount to shift the selection by',
            type=lambda value: RelativePts(api, value),
            required=True,
        )
        parser.add_argument(
            '--no-align',
            help='don\'t realign selection to video frames',
            action='store_true'
        )

        group = parser.add_mutually_exclusive_group()
        group.add_argument(
            '--start',
            action='store_const',
            dest='method',
            const='start',
            help='shift selection start',
            default='both'
        )
        group.add_argument(
            '--end',
            action='store_const',
            dest='method',
            const='end',
            help='shift selection end'
        )
        group.add_argument(
            '--both',
            action='store_const',
            dest='method',
            const='both',
            help='shift whole selection'
        )


class AudioCommitSelectionCommand(BaseCommand):
    names = [
        'audio-commit-sel',
        'audio-commit-selection',
        'spectrogram-commit-sel',
        'spectrogram-commit-selection'
    ]
    help_text = (
        'Commits the spectrogram selection into given subtitles. '
        'The subtitles start and end times are synced to the '
        'current spectrogram selection boundaries.'
    )

    @property
    def is_enabled(self) -> bool:
        return self.args.target.makes_sense

    async def run(self) -> None:
        with self.api.undo.capture():
            subs = await self.args.target.get_subtitles()
            if not subs:
                raise CommandUnavailable('nothing to update')

            for sub in subs:
                sub.begin_update()
                sub.start = self.api.media.audio.selection_start
                sub.end = self.api.media.audio.selection_end
                sub.end_update()

    @staticmethod
    def _decorate_parser(
            api: bubblesub.api.Api,
            parser: argparse.ArgumentParser
    ) -> None:
        parser.add_argument(
            '-t', '--target',
            help='subtitles to commit selection into',
            type=lambda value: EventSelection(api, value),
            default='selected'
        )


def register(cmd_api: bubblesub.api.cmd.CommandApi) -> None:
    """
    Register commands in this file into the command API.

    :param cmd_api: command API
    """
    for cls in [
            AudioScrollCommand,
            AudioZoomCommand,
            AudioShiftSelectionCommand,
            AudioCommitSelectionCommand,
    ]:
        cmd_api.register_core_command(T.cast(T.Type[BaseCommand], cls))
