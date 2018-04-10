import typing as T

import ffms
import pyfftw
import numpy as np
from PyQt5 import QtCore

import bubblesub.api
import bubblesub.provider


DERIVATION_SIZE = 10
DERIVATION_DISTANCE = 6
TSpectrumProviderResult = T.Tuple[int, T.List[int]]


class SpectrumProviderContext(
        bubblesub.provider.ProviderContext[int, TSpectrumProviderResult]):
    def __init__(self, api: bubblesub.api.Api) -> None:
        super().__init__()
        self._api = api
        self._input = pyfftw.empty_aligned(
            2 << DERIVATION_SIZE, dtype=np.float32)
        self._output = pyfftw.empty_aligned(
            (1 << DERIVATION_SIZE) + 1, dtype=np.complex64)
        self._fftw = pyfftw.FFTW(
            self._input, self._output, flags=('FFTW_MEASURE',))

    def work(self, task: int) -> TSpectrumProviderResult:
        pts = task

        audio_frame = int(pts * self._api.media.audio.sample_rate / 1000.0)
        first_sample = (
            audio_frame >> DERIVATION_DISTANCE) << DERIVATION_DISTANCE
        sample_count = 2 << DERIVATION_SIZE

        samples = self._api.media.audio.get_samples(first_sample, sample_count)
        samples = np.mean(samples, axis=1)
        sample_fmt = self._api.media.audio.sample_format
        if sample_fmt is None:
            return (pts, np.zeros((1 << DERIVATION_SIZE) + 1))
        elif sample_fmt == ffms.FFMS_FMT_S16:
            samples /= 32768.
        elif sample_fmt == ffms.FFMS_FMT_S32:
            samples /= 4294967296.
        elif sample_fmt not in (ffms.FFMS_FMT_FLT, ffms.FFMS_FMT_DBL):
            raise RuntimeError('Unknown sample format: {}'.format(sample_fmt))

        self._input[0:len(samples)] = samples
        out = self._fftw()

        scale_factor = 9 / np.sqrt(1 * (1 << DERIVATION_SIZE))
        out = np.log(
            np.sqrt(
                np.real(out) * np.real(out)
                + np.imag(out) * np.imag(out)
            ) * scale_factor + 1)

        out *= 255
        out = np.clip(out, 0, 255)
        out = np.flip(out, axis=0)
        out = out.astype(dtype=np.uint8)
        return (pts, out)


class SpectrumProvider(bubblesub.provider.Provider[SpectrumProviderContext]):
    def __init__(
            self,
            parent: QtCore.QObject,
            api: bubblesub.api.Api,
    ) -> None:
        super().__init__(parent, SpectrumProviderContext(api))
