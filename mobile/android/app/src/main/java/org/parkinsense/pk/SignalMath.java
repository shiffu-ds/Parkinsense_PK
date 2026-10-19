package org.parkinsense.pk;

/** Measured recording signals; these are not symptoms or diagnostic scores. */
final class SignalMath {
    private SignalMath() {}

    static final class AudioMetrics {
        final double rms;
        final double dbfs;
        final double clippedPercent;
        final boolean quiet;

        AudioMetrics(double rms, double dbfs, double clippedPercent) {
            this.rms = rms;
            this.dbfs = dbfs;
            this.clippedPercent = clippedPercent;
            this.quiet = dbfs < -45.0;
        }
    }

    static AudioMetrics audio(short[] samples, int length) {
        if (length < 1 || length > samples.length) {
            throw new IllegalArgumentException("Invalid sample count");
        }
        double squares = 0;
        int clipped = 0;
        for (int i = 0; i < length; i++) {
            int sample = samples[i];
            squares += (double) sample * sample;
            if (Math.abs(sample) >= 32700) clipped++;
        }
        double rms = Math.sqrt(squares / length) / 32768.0;
        double dbfs = rms == 0 ? -120.0 : Math.max(-120.0, 20.0 * Math.log10(rms));
        return new AudioMetrics(rms, dbfs, 100.0 * clipped / length);
    }

    static final class ImageMetrics {
        final double brightnessPercent;
        final double contrast;
        final double edgeDetail;
        final double frameChangePercent;

        ImageMetrics(double brightnessPercent, double contrast, double edgeDetail,
                     double frameChangePercent) {
            this.brightnessPercent = brightnessPercent;
            this.contrast = contrast;
            this.edgeDetail = edgeDetail;
            this.frameChangePercent = frameChangePercent;
        }
    }

    static ImageMetrics image(int[] luma, int width, int height, int[] previous) {
        if (width < 2 || height < 2 || luma.length != width * height) {
            throw new IllegalArgumentException("Invalid luminance grid");
        }
        double sum = 0;
        double squares = 0;
        double edge = 0;
        double difference = 0;
        int edges = 0;
        boolean hasPrevious = previous != null && previous.length == luma.length;
        for (int y = 0; y < height; y++) {
            for (int x = 0; x < width; x++) {
                int i = y * width + x;
                int value = luma[i];
                if (value < 0 || value > 255) throw new IllegalArgumentException("Invalid luma");
                sum += value;
                squares += (double) value * value;
                if (x > 0) { edge += Math.abs(value - luma[i - 1]); edges++; }
                if (y > 0) { edge += Math.abs(value - luma[i - width]); edges++; }
                if (hasPrevious) difference += Math.abs(value - previous[i]);
            }
        }
        double mean = sum / luma.length;
        double contrast = Math.sqrt(Math.max(0, squares / luma.length - mean * mean));
        return new ImageMetrics(mean / 255.0 * 100.0, contrast, edge / edges,
                hasPrevious ? difference / (255.0 * luma.length) * 100.0 : Double.NaN);
    }
}
