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

"""ASS file writer."""

import typing as T
from collections import OrderedDict

from bubblesub.ass.event import Event
from bubblesub.ass.file import AssFile
from bubblesub.ass.style import Color
from bubblesub.ass.style import Style
from bubblesub.ass.util import escape_ass_tag
from bubblesub.util import ms_to_times

NOTICE = 'Script generated by bubblesub\nhttps://github.com/rr-/bubblesub'


def _serialize_color(col: Color) -> str:
    return f'&H{col.alpha:02X}{col.blue:02X}{col.green:02X}{col.red:02X}'


def _ms_to_timestamp(milliseconds: int) -> str:
    hours, minutes, seconds, milliseconds = ms_to_times(milliseconds)
    return f'{hours:01d}:{minutes:02d}:{seconds:02d}.{milliseconds // 10:02d}'


def _write_info(ass_file: AssFile, handle: T.IO) -> None:
    info = OrderedDict()
    info['ScriptType'] = 'sentinel'  # make sure script type is the first entry
    info.update(ass_file.info)
    info['ScriptType'] = 'v4.00+'
    for key, value in info.items():
        print(key, value, sep=': ', file=handle)


def _write_styles(ass_file: AssFile, handle: T.IO) -> None:
    print('\n[V4+ Styles]', file=handle)
    print(
        'Format: Name, Fontname, Fontsize, PrimaryColour, '
        'SecondaryColour, OutlineColour, BackColour, Bold, Italic, '
        'Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, '
        'BorderStyle, Outline, Shadow, Alignment, '
        'MarginL, MarginR, MarginV, Encoding',
        file=handle
    )
    for style in ass_file.styles:
        _write_style(style, handle)


def _write_style(style: Style, handle: T.IO) -> None:
    print('Style: ' + ','.join([
        style.name,
        style.font_name,
        f'{style.font_size:}',
        _serialize_color(style.primary_color),
        _serialize_color(style.secondary_color),
        _serialize_color(style.outline_color),
        _serialize_color(style.back_color),
        '-1' if style.bold else '0',
        '-1' if style.italic else '0',
        '-1' if style.underline else '0',
        '-1' if style.strike_out else '0',
        f'{style.scale_x:}',
        f'{style.scale_y:}',
        f'{style.spacing:}',
        f'{style.angle:}',
        f'{style.border_style:d}',
        f'{style.outline:}',
        f'{style.shadow:}',
        f'{style.alignment:d}',
        f'{style.margin_left:d}',
        f'{style.margin_right:d}',
        f'{style.margin_vertical:d}',
        f'{style.encoding:d}',
    ]), file=handle)


def _write_events(ass_file: AssFile, handle: T.IO) -> None:
    print('\n[Events]', file=handle)
    print(
        'Format: Layer, Start, End, Style, Name, '
        'MarginL, MarginR, MarginV, Effect, Text',
        file=handle
    )
    for event in ass_file.events:
        _write_event(event, handle)


def _write_event(event: Event, handle: T.IO) -> None:
    text = event.text

    if event.start is not None and event.end is not None:
        text = '{TIME:%d,%d}' % (event.start, event.end) + text

    if event.note:
        text += '{NOTE:%s}' % escape_ass_tag(event.note.replace('\n', '\\N'))

    event_type = 'Comment' if event.is_comment else 'Dialogue'
    print(event_type + ': ' + ','.join([
        f'{event.layer:d}',
        _ms_to_timestamp(event.start),
        _ms_to_timestamp(event.end),
        event.style,
        event.actor,
        f'{event.margin_left:d}',
        f'{event.margin_right:d}',
        f'{event.margin_vertical:d}',
        event.effect,
        text,
    ]), file=handle)


def write_ass(ass_file: AssFile, handle: T.IO) -> None:
    """
    Save ASS to the specified target.

    :param ass_file: file to save
    :param handle: writable stream
    """
    print("[Script Info]", file=handle)
    for line in NOTICE.splitlines(False):
        print(";", line, file=handle)

    _write_info(ass_file, handle)
    _write_styles(ass_file, handle)
    _write_events(ass_file, handle)
