package org.parkinsense.pk;

import org.junit.Test;

import static org.junit.Assert.*;

public class SignalMathTest {
    @Test public void silenceIsFiniteAndQuiet() {
        SignalMath.AudioMetrics signal = SignalMath.audio(new short[1600], 1600);
        assertEquals(0.0, signal.rms, 0.0);
        assertEquals(-120.0, signal.dbfs, 0.0);
        assertEquals(0.0, signal.clippedPercent, 0.0);
        assertTrue(signal.quiet);
    }

    @Test public void generatedHalfScaleToneHasCalibratedRms() {
        short[] samples = new short[1600];
        for (int i = 0; i < samples.length; i++) {
            samples[i] = (short) Math.round(16384.0 * Math.sin(2.0 * Math.PI * 200.0 * i / 16000.0));
        }
        SignalMath.AudioMetrics signal = SignalMath.audio(samples, samples.length);
        assertEquals(0.5 / Math.sqrt(2), signal.rms, 0.0001);
        assertEquals(-9.0309, signal.dbfs, 0.002);
        assertEquals(0.0, signal.clippedPercent, 0.0);
        assertFalse(signal.quiet);
    }

    @Test public void clippingDetectsBothInt16Endpoints() {
        SignalMath.AudioMetrics signal = SignalMath.audio(new short[]{32767, -32768, 0, 0}, 4);
        assertEquals(50.0, signal.clippedPercent, 0.0);
    }

    @Test public void darkAndUniformFramesHaveNoEdgesOrContrast() {
        SignalMath.ImageMetrics signal = SignalMath.image(new int[4], 2, 2, null);
        assertEquals(0.0, signal.brightnessPercent, 0.0);
        assertEquals(0.0, signal.edgeDetail, 0.0);
        assertEquals(0.0, signal.contrast, 0.0);
        assertTrue(Double.isNaN(signal.frameChangePercent));
    }

    @Test public void fullScaleFrameChangeUsesPixelRangeAndNotSymptomScale() {
        int[] bright = new int[]{255, 255, 255, 255};
        SignalMath.ImageMetrics signal = SignalMath.image(bright, 2, 2, new int[4]);
        assertEquals(100.0, signal.brightnessPercent, 0.0);
        assertEquals(100.0, signal.frameChangePercent, 0.0);
        assertEquals(0.0, signal.edgeDetail, 0.0);
    }

    @Test public void unchangedCheckerboardHasDetailButNoFrameChange() {
        int[] grid = new int[]{0, 255, 255, 0};
        SignalMath.ImageMetrics signal = SignalMath.image(grid, 2, 2, grid);
        assertEquals(50.0, signal.brightnessPercent, 0.0);
        assertEquals(127.5, signal.contrast, 0.0);
        assertEquals(255.0, signal.edgeDetail, 0.0);
        assertEquals(0.0, signal.frameChangePercent, 0.0);
    }

    @Test(expected = IllegalArgumentException.class)
    public void emptyAudioDoesNotPresentInventedMeasurements() {
        SignalMath.audio(new short[0], 0);
    }
}
