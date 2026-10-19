package org.parkinsense.pk;

import android.Manifest;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.graphics.Rect;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.media.AudioFormat;
import android.media.AudioRecord;
import android.media.MediaRecorder;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.util.Size;
import android.view.Gravity;
import android.view.View;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.ScrollView;
import android.widget.TextView;

import androidx.activity.ComponentActivity;
import androidx.activity.OnBackPressedCallback;
import androidx.annotation.NonNull;
import androidx.camera.core.CameraSelector;
import androidx.camera.core.ImageAnalysis;
import androidx.camera.core.ImageProxy;
import androidx.camera.core.Preview;
import androidx.camera.lifecycle.ProcessCameraProvider;
import androidx.camera.video.FallbackStrategy;
import androidx.camera.video.FileOutputOptions;
import androidx.camera.video.Quality;
import androidx.camera.video.QualitySelector;
import androidx.camera.video.Recorder;
import androidx.camera.video.Recording;
import androidx.camera.video.VideoCapture;
import androidx.camera.video.VideoRecordEvent;
import androidx.camera.view.PreviewView;
import androidx.core.content.ContextCompat;
import androidx.core.graphics.Insets;
import androidx.core.view.ViewCompat;
import androidx.core.view.WindowInsetsCompat;

import com.google.common.util.concurrent.ListenableFuture;

import java.io.File;
import java.io.IOException;
import java.io.RandomAccessFile;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;

/** Native private capture with actual on-device signal checks during recording. */
public final class LiveCheckerActivity extends ComponentActivity {
    public static final String EXTRA_MODE = "mode";
    public static final String EXTRA_TASK_CODE = "task_code";
    public static final String EXTRA_TASK_NAME = "task_name";
    public static final String EXTRA_RECORDING_PATH = "recording_path";
    public static final String EXTRA_MIME_TYPE = "mime_type";

    private static final long MAX_DURATION_MS = 45_000;
    private static final long MAX_BYTES = 30L * 1024 * 1024;
    private static final int SAMPLE_RATE = 16_000;
    private static final int PERMISSION_REQUEST = 501;
    private static final int BACKGROUND = 0xff101522;
    private static final int PANEL = 0xff1b2330;
    private static final int TEXT = 0xffeaf0f7;
    private static final int MUTED = 0xffa6b4c6;
    private static final int ACCENT = 0xff70d9c7;
    private enum State { IDLE, PREPARING, RECORDING, STOPPING, READY }

    private final Handler main = new Handler(Looper.getMainLooper());
    private final ExecutorService cameraExecutor = Executors.newFixedThreadPool(2);
    private final ExecutorService audioExecutor = Executors.newSingleThreadExecutor();
    private volatile State state = State.IDLE;
    private volatile int generation = 0;
    private int permissionGeneration = -1;
    private boolean visible;
    private boolean returned;
    private String mode;
    private String taskCode;
    private String taskName;
    private File readyClip;
    private ProcessCameraProvider cameraProvider;
    private VideoSession videoSession;
    private AudioSession audioSession;
    private PreviewView preview;
    private TextView status;
    private TextView timer;
    private TextView measurements;
    private ProgressBar level;
    private Button start;
    private Button stop;
    private Button use;
    private Button discard;
    private long recordingStartedAt;

    private static final class VideoSession {
        final int generation;
        final File file;
        Recording recording;
        boolean discarded;
        VideoSession(int generation, File file) { this.generation = generation; this.file = file; }
    }

    private static final class AudioSession {
        final int generation;
        final File file;
        final AudioRecord recorder;
        final AtomicBoolean running = new AtomicBoolean(true);
        volatile boolean discarded;
        AudioSession(int generation, File file, AudioRecord recorder) {
            this.generation = generation; this.file = file; this.recorder = recorder;
        }
    }

    @Override protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_SECURE);
        setResult(RESULT_CANCELED);
        mode = "audio".equals(getIntent().getStringExtra(EXTRA_MODE)) ? "audio" : "video";
        taskCode = getIntent().getStringExtra(EXTRA_TASK_CODE);
        if (taskCode == null) taskCode = getIntent().getStringExtra("task");
        taskName = getIntent().getStringExtra(EXTRA_TASK_NAME);
        if (taskName == null || taskName.trim().isEmpty()) taskName = "audio".equals(mode) ? "Voice recording" : "Movement recording";
        if (taskCode == null || taskCode.trim().isEmpty()) {
            finish();
            return;
        }
        buildInterface();
        getOnBackPressedDispatcher().addCallback(this, new OnBackPressedCallback(true) {
            @Override public void handleOnBackPressed() { cancelCapture(true); finish(); }
        });
    }

    private void buildInterface() {
        getWindow().setStatusBarColor(BACKGROUND);
        getWindow().setNavigationBarColor(BACKGROUND);
        ScrollView scroll = new ScrollView(this);
        scroll.setBackgroundColor(BACKGROUND);
        scroll.setFillViewport(true);
        LinearLayout content = new LinearLayout(this);
        content.setOrientation(LinearLayout.VERTICAL);
        content.setPadding(dp(20), dp(20), dp(20), dp(24));
        scroll.addView(content);
        setContentView(scroll);
        ViewCompat.setOnApplyWindowInsetsListener(scroll, (view, insets) -> {
            Insets bars = insets.getInsets(WindowInsetsCompat.Type.systemBars());
            view.setPadding(bars.left, bars.top, bars.right, bars.bottom);
            return insets;
        });
        ViewCompat.requestApplyInsets(scroll);
        Button back = button("Back", false);
        back.setOnClickListener(v -> { cancelCapture(true); finish(); });
        content.addView(back, spaced());
        content.addView(label("Live Checker", 29, TEXT, true), spaced());
        content.addView(label(taskName, 18, ACCENT, true), spaced());
        String instructions = "audio".equals(mode)
                ? "Keep the phone close and speak comfortably. Microphone access begins only when you tap Start."
                : "Use a steady phone and good lighting. Perform this activity only if it is safe for you. Camera access begins only when you tap Start.";
        content.addView(label(instructions, 15, MUTED, false), spaced());
        TextView taskGuidance = label(recordingGuidance(taskCode), 15, TEXT, false);
        taskGuidance.setPadding(dp(16), dp(14), dp(16), dp(14));
        taskGuidance.setBackground(panel());
        content.addView(taskGuidance, spaced());
        if ("video".equals(mode)) {
            preview = new PreviewView(this);
            preview.setImplementationMode(PreviewView.ImplementationMode.COMPATIBLE);
            preview.setScaleType(PreviewView.ScaleType.FIT_CENTER);
            preview.setBackgroundColor(Color.BLACK);
            preview.setContentDescription("Live camera preview");
            content.addView(preview, new LinearLayout.LayoutParams(-1, dp(255)));
        } else {
            TextView microphone = label("MICROPHONE\nLive sound level", 22, ACCENT, true);
            microphone.setGravity(Gravity.CENTER);
            microphone.setPadding(dp(20), dp(35), dp(20), dp(35));
            microphone.setBackground(panel());
            content.addView(microphone, spaced());
        }
        LinearLayout signals = new LinearLayout(this);
        signals.setOrientation(LinearLayout.VERTICAL);
        signals.setPadding(dp(18), dp(16), dp(18), dp(16));
        signals.setBackground(panel());
        status = label("Ready to record", 17, ACCENT, true);
        status.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);
        timer = label("00:00 / 00:45", 24, TEXT, true);
        measurements = label("Live measurements appear during recording.", 15, TEXT, false);
        signals.addView(status, spaced());
        signals.addView(timer, spaced());
        signals.addView(measurements, spaced());
        if ("audio".equals(mode)) {
            level = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
            level.setMax(100);
            level.setProgressTintList(android.content.res.ColorStateList.valueOf(ACCENT));
            level.setContentDescription("Measured microphone level");
            signals.addView(level, new LinearLayout.LayoutParams(-1, dp(12)));
        }
        content.addView(signals, spaced());
        content.addView(label("Checks run on this phone. They describe recording signals and cannot diagnose Parkinson’s disease or measure symptom severity.", 13, MUTED, false), spaced());
        start = button("Start live recording", true);
        stop = button("Stop recording", false);
        use = button("Use recording", true);
        discard = button("Discard recording", false);
        start.setOnClickListener(v -> startTapped());
        stop.setOnClickListener(v -> stopCapture());
        use.setOnClickListener(v -> returnRecording());
        discard.setOnClickListener(v -> cancelCapture(false));
        content.addView(start, spaced());
        content.addView(stop, spaced());
        content.addView(use, spaced());
        content.addView(discard, spaced());
        content.addView(label("Recordings stay in temporary app storage until you choose Use recording. Nothing is uploaded here. Leaving this screen discards any unfinished or unused recording.", 13, MUTED, false), spaced());
        updateButtons();
    }

    private void startTapped() {
        if (state != State.IDLE || videoSession != null || audioSession != null || !visible) return;
        int token = ++generation;
        state = State.PREPARING;
        status.setText("Preparing recording…");
        status.setTextColor(ACCENT);
        measurements.setText("Waiting for live signal…");
        timer.setText("00:00 / 00:45");
        updateButtons();
        String permission = "audio".equals(mode) ? Manifest.permission.RECORD_AUDIO : Manifest.permission.CAMERA;
        if (ContextCompat.checkSelfPermission(this, permission) != PackageManager.PERMISSION_GRANTED) {
            permissionGeneration = token;
            requestPermissions(new String[]{permission}, PERMISSION_REQUEST);
        } else beginCapture(token);
    }

    @Override public void onRequestPermissionsResult(int requestCode, @NonNull String[] permissions,
                                                      @NonNull int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode != PERMISSION_REQUEST) return;
        int token = permissionGeneration;
        permissionGeneration = -1;
        if (!owns(token) || state != State.PREPARING) return;
        if (grantResults.length == 1 && grantResults[0] == PackageManager.PERMISSION_GRANTED) beginCapture(token);
        else fail("Permission was not granted. You can try again or upload a recorded clip from the previous screen.");
    }

    private boolean owns(int token) { return token == generation && visible && !isFinishing() && !isDestroyed(); }

    private void beginCapture(int token) {
        if (!owns(token) || state != State.PREPARING) return;
        if ("audio".equals(mode)) beginAudio(token); else beginVideo(token);
    }

    private void beginVideo(int token) {
        ListenableFuture<ProcessCameraProvider> future = ProcessCameraProvider.getInstance(this);
        future.addListener(() -> {
            if (!owns(token) || state != State.PREPARING) return;
            try {
                cameraProvider = future.get();
                cameraProvider.unbindAll();
                Preview cameraPreview = new Preview.Builder().build();
                cameraPreview.setSurfaceProvider(preview.getSurfaceProvider());
                Recorder recorder = new Recorder.Builder()
                        .setQualitySelector(QualitySelector.from(Quality.SD,
                                FallbackStrategy.lowerQualityOrHigherThan(Quality.SD)))
                        .build();
                VideoCapture<Recorder> capture = VideoCapture.withOutput(recorder);
                ImageAnalysis analysis = new ImageAnalysis.Builder()
                        .setTargetResolution(new Size(640, 480))
                        .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                        .build();
                analysis.setAnalyzer(cameraExecutor, new LumaAnalyzer(token));
                // Bind every required use case together. A failed combination is never presented as live analysis.
                cameraProvider.bindToLifecycle(this, CameraSelector.DEFAULT_BACK_CAMERA,
                        cameraPreview, capture, analysis);
                File clip = File.createTempFile("ps-video-", ".mp4", getCacheDir());
                VideoSession session = new VideoSession(token, clip);
                videoSession = session;
                FileOutputOptions options = new FileOutputOptions.Builder(clip)
                        .setDurationLimitMillis(MAX_DURATION_MS)
                        .setFileSizeLimit(MAX_BYTES)
                        .build();
                // Movement clips have no audio track: only the camera permission is requested.
                session.recording = recorder.prepareRecording(this, options)
                        .start(ContextCompat.getMainExecutor(this), event -> handleVideoEvent(session, event));
            } catch (Exception error) {
                VideoSession pending = videoSession;
                if (pending != null && pending.generation == token) {
                    pending.discarded = true;
                    delete(pending.file);
                    videoSession = null;
                }
                unbindCamera();
                if (owns(token)) fail("Live camera recording with analysis is unavailable on this device. Return and upload a recorded clip instead.");
            }
        }, ContextCompat.getMainExecutor(this));
    }

    private void handleVideoEvent(VideoSession session, VideoRecordEvent event) {
        if (event instanceof VideoRecordEvent.Finalize) {
            boolean current = videoSession == session;
            if (current) { videoSession = null; unbindCamera(); }
            session.recording = null;
            VideoRecordEvent.Finalize result = (VideoRecordEvent.Finalize) event;
            int error = result.getError();
            boolean usable = error == VideoRecordEvent.Finalize.ERROR_NONE
                    || error == VideoRecordEvent.Finalize.ERROR_DURATION_LIMIT_REACHED
                    || error == VideoRecordEvent.Finalize.ERROR_FILE_SIZE_LIMIT_REACHED;
            long durationMs = result.getRecordingStats().getRecordedDurationNanos() / 1_000_000;
            if (!current || !owns(session.generation) || session.discarded) {
                delete(session.file);
                if (current && !isFinishing() && !isDestroyed()) settleAfterDiscard();
                return;
            }
            main.removeCallbacks(tick);
            getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
            if (!usable || session.file.length() == 0 || session.file.length() > MAX_BYTES || durationMs < 2_000) {
                delete(session.file);
                fail(durationMs < 2_000 && usable ? "Recording was too short. Record at least 2 seconds and try again."
                        : "The camera could not finish this recording. Try again or upload a clip.");
            } else recordingReady(session.file, durationMs);
        } else if (videoSession == session && owns(session.generation) && !session.discarded) {
            if (event instanceof VideoRecordEvent.Start) recordingStarted();
            else if (event instanceof VideoRecordEvent.Status) {
                long ms = event.getRecordingStats().getRecordedDurationNanos() / 1_000_000;
                timer.setText(formatTime(ms) + " / 00:45");
            }
        }
    }

    private final class LumaAnalyzer implements ImageAnalysis.Analyzer {
        private final int token;
        private long lastSample;
        private int[] previous;
        LumaAnalyzer(int token) { this.token = token; }
        @Override public void analyze(@NonNull ImageProxy image) {
            try {
                long now = SystemClock.elapsedRealtime();
                if (token != generation || state != State.RECORDING || now - lastSample < 500) return;
                lastSample = now;
                Rect crop = image.getCropRect();
                int width = Math.min(80, crop.width());
                int height = Math.min(60, crop.height());
                if (width < 2 || height < 2) return;
                ImageProxy.PlaneProxy plane = image.getPlanes()[0];
                ByteBuffer buffer = plane.getBuffer().duplicate();
                int offset = buffer.position();
                int[] luma = new int[width * height];
                for (int y = 0; y < height; y++) {
                    int sourceY = crop.top + y * crop.height() / height;
                    for (int x = 0; x < width; x++) {
                        int sourceX = crop.left + x * crop.width() / width;
                        int index = offset + sourceY * plane.getRowStride() + sourceX * plane.getPixelStride();
                        luma[y * width + x] = buffer.get(index) & 0xff;
                    }
                }
                SignalMath.ImageMetrics signals = SignalMath.image(luma, width, height, previous);
                previous = luma;
                main.post(() -> {
                    if (!owns(token) || state != State.RECORDING) return;
                    String change = Double.isNaN(signals.frameChangePercent) ? "collecting…"
                            : String.format(Locale.US, "%.1f%%", signals.frameChangePercent);
                    measurements.setText(String.format(Locale.US,
                            "Brightness  %.0f%%\nContrast  %.1f / 255\nEdge detail  %.1f / 255\nPixel change  %s\n\nPixel change includes camera movement. These values are not body movement or symptom scores.",
                            signals.brightnessPercent, signals.contrast, signals.edgeDetail, change));
                });
            } catch (RuntimeException error) {
                main.post(() -> {
                    if (owns(token) && state == State.RECORDING) measurements.setText("This camera frame could not be analysed. Waiting for the next frame…");
                });
            } finally { image.close(); }
        }
    }

    private void beginAudio(int token) {
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO)
                != PackageManager.PERMISSION_GRANTED) {
            if (owns(token)) fail("Microphone permission is required. Tap Start and grant permission, or upload an audio clip instead.");
            return;
        }
        AudioRecord recorder = null;
        File clip = null;
        try {
            int minBuffer = AudioRecord.getMinBufferSize(SAMPLE_RATE, AudioFormat.CHANNEL_IN_MONO,
                    AudioFormat.ENCODING_PCM_16BIT);
            if (minBuffer <= 0) throw new IOException("Unsupported microphone format");
            recorder = new AudioRecord.Builder()
                    .setAudioSource(MediaRecorder.AudioSource.VOICE_RECOGNITION)
                    .setAudioFormat(new AudioFormat.Builder().setSampleRate(SAMPLE_RATE)
                            .setChannelMask(AudioFormat.CHANNEL_IN_MONO)
                            .setEncoding(AudioFormat.ENCODING_PCM_16BIT).build())
                    .setBufferSizeInBytes(Math.max(minBuffer * 2, 8192)).build();
            if (recorder.getState() != AudioRecord.STATE_INITIALIZED) throw new IOException("Microphone unavailable");
            clip = File.createTempFile("ps-audio-", ".wav", getCacheDir());
            AudioSession session = new AudioSession(token, clip, recorder);
            recorder.startRecording();
            if (recorder.getRecordingState() != AudioRecord.RECORDSTATE_RECORDING) throw new IOException("Microphone did not start");
            audioSession = session;
            recordingStarted();
            audioExecutor.execute(() -> writeAudio(session));
        } catch (SecurityException permissionRevoked) {
            audioStartupFailed(token, recorder, clip,
                    "Microphone permission changed before recording started. Grant permission and try again.");
        } catch (Exception error) {
            audioStartupFailed(token, recorder, clip,
                    "The microphone could not start. Check microphone permission or upload an audio clip instead.");
        }
    }

    private void audioStartupFailed(int token, AudioRecord recorder, File clip, String message) {
        if (audioSession != null && audioSession.generation == token) audioSession = null;
        if (recorder != null) { try { recorder.release(); } catch (RuntimeException ignored) {} }
        delete(clip);
        if (owns(token)) fail(message);
    }

    private void writeAudio(AudioSession session) {
        long pcmBytes = 0;
        String error = null;
        long lastUpdate = 0;
        short[] samples = new short[1600];
        ByteBuffer bytes = ByteBuffer.allocate(samples.length * 2).order(ByteOrder.LITTLE_ENDIAN);
        try (RandomAccessFile output = new RandomAccessFile(session.file, "rw")) {
            output.write(new byte[44]);
            while (session.running.get() && pcmBytes < SAMPLE_RATE * 2L * MAX_DURATION_MS / 1000) {
                int count = session.recorder.read(samples, 0, samples.length, AudioRecord.READ_BLOCKING);
                if (count < 0) {
                    if (session.running.get()) throw new IOException("Microphone read failed");
                    break;
                }
                if (count == 0) continue;
                int allowed = (int) Math.min(count, (SAMPLE_RATE * 2L * MAX_DURATION_MS / 1000 - pcmBytes) / 2);
                bytes.clear();
                for (int i = 0; i < allowed; i++) bytes.putShort(samples[i]);
                output.write(bytes.array(), 0, allowed * 2);
                pcmBytes += allowed * 2L;
                long now = SystemClock.elapsedRealtime();
                if (now - lastUpdate >= 200) {
                    lastUpdate = now;
                    SignalMath.AudioMetrics signal = SignalMath.audio(samples, allowed);
                    main.post(() -> {
                        if (!owns(session.generation) || state != State.RECORDING) return;
                        measurements.setText(String.format(Locale.US,
                                "RMS level  %.4f\nSound level  %.1f dBFS\nNear-full-scale samples  %.1f%%\n%s",
                                signal.rms, signal.dbfs, signal.clippedPercent,
                                signal.quiet ? "Quiet signal — move closer or speak comfortably." : "Microphone signal detected."));
                        level.setProgress((int) Math.max(0, Math.min(100, (signal.dbfs + 60) / 60 * 100)));
                    });
                }
            }
            writeWavHeader(output, pcmBytes);
            output.getFD().sync();
        } catch (SecurityException permissionRevoked) {
            error = "Microphone permission changed during recording. Grant permission and try again.";
        } catch (Exception failure) { error = "The audio recording could not be completed. Please try again."; }
        finally {
            session.running.set(false);
            try { session.recorder.stop(); } catch (RuntimeException ignored) {}
            try { session.recorder.release(); } catch (RuntimeException ignored) {}
        }
        final long duration = pcmBytes * 1000 / (SAMPLE_RATE * 2L);
        final String failure = error;
        if (session.discarded) delete(session.file);
        main.post(() -> {
            boolean current = audioSession == session;
            if (current) audioSession = null;
            if (!current || !owns(session.generation) || session.discarded) {
                delete(session.file);
                if (current && !isFinishing() && !isDestroyed()) settleAfterDiscard();
                return;
            }
            main.removeCallbacks(tick);
            getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
            if (failure != null || duration < 2_000 || session.file.length() > MAX_BYTES) {
                delete(session.file);
                fail(failure != null ? failure : "Recording was too short. Record at least 2 seconds and try again.");
            } else recordingReady(session.file, duration);
        });
    }

    private static void writeWavHeader(RandomAccessFile output, long pcmBytes) throws IOException {
        ByteBuffer header = ByteBuffer.allocate(44).order(ByteOrder.LITTLE_ENDIAN);
        header.put("RIFF".getBytes(StandardCharsets.US_ASCII));
        header.putInt((int) (36 + pcmBytes));
        header.put("WAVEfmt ".getBytes(StandardCharsets.US_ASCII));
        header.putInt(16).putShort((short) 1).putShort((short) 1);
        header.putInt(SAMPLE_RATE).putInt(SAMPLE_RATE * 2);
        header.putShort((short) 2).putShort((short) 16);
        header.put("data".getBytes(StandardCharsets.US_ASCII)).putInt((int) pcmBytes);
        output.seek(0);
        output.write(header.array());
    }

    private void recordingStarted() {
        state = State.RECORDING;
        recordingStartedAt = SystemClock.elapsedRealtime();
        status.setText("● LIVE — Recording and analysing");
        status.setTextColor(ACCENT);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        main.removeCallbacks(tick);
        main.post(tick);
        updateButtons();
    }

    private final Runnable tick = new Runnable() {
        @Override public void run() {
            if (state != State.RECORDING || !visible) return;
            long elapsed = SystemClock.elapsedRealtime() - recordingStartedAt;
            timer.setText(formatTime(elapsed) + " / 00:45");
            if (elapsed >= MAX_DURATION_MS) stopCapture();
            else main.postDelayed(this, 200);
        }
    };

    private void stopCapture() {
        if (state != State.RECORDING) return;
        state = State.STOPPING;
        status.setText("Finishing recording…");
        main.removeCallbacks(tick);
        getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        if (videoSession != null && videoSession.recording != null) {
            try { videoSession.recording.stop(); }
            catch (RuntimeException failure) {
                VideoSession failed = videoSession;
                failed.discarded = true;
                videoSession = null;
                delete(failed.file);
                unbindCamera();
                fail("The camera could not finish this recording. Please try again.");
            }
        }
        if (audioSession != null) stopAudio(audioSession);
        updateButtons();
    }

    private void recordingReady(File file, long durationMs) {
        readyClip = file;
        state = State.READY;
        status.setText("Recording ready — choose Use or Discard");
        timer.setText(formatTime(durationMs) + " recorded");
        updateButtons();
    }

    private void returnRecording() {
        if (state != State.READY || readyClip == null || !readyClip.isFile() || !visible) return;
        Intent result = new Intent();
        result.putExtra(EXTRA_RECORDING_PATH, readyClip.getAbsolutePath());
        result.putExtra(EXTRA_MIME_TYPE, "audio".equals(mode) ? "audio/wav" : "video/mp4");
        result.putExtra(EXTRA_TASK_CODE, taskCode);
        returned = true;
        readyClip = null;
        setResult(RESULT_OK, result);
        finish();
    }

    private void cancelCapture(boolean leaving) {
        generation++;
        permissionGeneration = -1;
        main.removeCallbacks(tick);
        getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        delete(readyClip);
        readyClip = null;
        if (videoSession != null) {
            videoSession.discarded = true;
            if (videoSession.recording != null) {
                try { videoSession.recording.stop(); } catch (RuntimeException ignored) {}
            }
            delete(videoSession.file);
        }
        if (audioSession != null) {
            audioSession.discarded = true;
            stopAudio(audioSession);
            delete(audioSession.file);
        }
        unbindCamera();
        state = State.IDLE;
        if (!leaving && status != null) {
            status.setText(videoSession != null || audioSession != null ? "Discarding recording…" : "Recording discarded");
            measurements.setText("Live measurements appear during recording.");
            timer.setText("00:00 / 00:45");
            if (level != null) level.setProgress(0);
            updateButtons();
        }
    }

    private static void stopAudio(AudioSession session) {
        session.running.set(false);
        try { session.recorder.stop(); } catch (RuntimeException ignored) {}
    }

    private void settleAfterDiscard() {
        state = State.IDLE;
        if (status != null) {
            status.setText("Recording discarded");
            updateButtons();
        }
    }

    private void fail(String message) {
        state = State.IDLE;
        status.setText(message);
        status.setTextColor(0xffffc982);
        getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        updateButtons();
    }

    private void unbindCamera() {
        if (cameraProvider != null) {
            try { cameraProvider.unbindAll(); } catch (RuntimeException ignored) {}
        }
    }

    @Override protected void onResume() { super.onResume(); visible = true; }

    @Override protected void onPause() {
        // Permission dialogs may pause the activity before any device is active.
        // Once capture exists, relinquish the devices as soon as another activity takes focus.
        if (!returned && (videoSession != null || audioSession != null)) cancelCapture(false);
        super.onPause();
    }

    @Override protected void onStop() {
        visible = false;
        if (!returned) cancelCapture(false);
        super.onStop();
    }

    @Override protected void onDestroy() {
        visible = false;
        if (!returned) cancelCapture(true);
        main.removeCallbacks(tick);
        cameraExecutor.shutdown();
        audioExecutor.shutdown();
        super.onDestroy();
    }

    private void updateButtons() {
        if (start == null) return;
        start.setEnabled(state == State.IDLE && videoSession == null && audioSession == null);
        start.setVisibility(state == State.READY ? View.GONE : View.VISIBLE);
        stop.setEnabled(state == State.RECORDING);
        stop.setVisibility(state == State.READY ? View.GONE : View.VISIBLE);
        use.setVisibility(state == State.READY ? View.VISIBLE : View.GONE);
        discard.setEnabled(state != State.IDLE || readyClip != null);
        start.setAlpha(start.isEnabled() ? 1f : 0.5f);
        stop.setAlpha(stop.isEnabled() ? 1f : 0.5f);
        discard.setAlpha(discard.isEnabled() ? 1f : 0.5f);
    }

    private static void delete(File file) {
        if (file != null && file.exists()) file.delete();
    }

    private String formatTime(long millis) {
        long seconds = Math.min(MAX_DURATION_MS, Math.max(0, millis)) / 1000;
        return String.format(Locale.US, "%02d:%02d", seconds / 60, seconds % 60);
    }

    private int dp(int value) { return (int) (value * getResources().getDisplayMetrics().density + 0.5f); }

    private static String recordingGuidance(String task) {
        switch (task) {
            case "gait":
                return "Place the phone steadily so your whole body fits in the frame. Walk at your usual comfortable pace in a clear space, with support nearby if needed. Stop if you feel unsteady.";
            case "turning":
                return "Keep your whole body in the frame. Turn at a comfortable pace in a clear space, only if you can do so safely. Keep support nearby if needed.";
            case "finger_left":
                return "Show your left hand clearly. Touch your thumb and index finger together repeatedly at a comfortable pace. Keep the phone steady.";
            case "finger_right":
                return "Show your right hand clearly. Touch your thumb and index finger together repeatedly at a comfortable pace. Keep the phone steady.";
            case "hand_open_close":
                return "Show your hand clearly. Open and close it at a comfortable pace without forcing the movement. Use the same hand for comparisons.";
            case "sit_to_stand":
                return "Use a sturdy chair in a clear space. Keep your whole body in view and support nearby. Stand and sit only if this is safe and comfortable for you.";
            case "reach":
                return "Stay steady or seated. Show your arm as you reach toward a nearby light object at a comfortable distance. Avoid stretching or losing balance.";
            case "grasp":
                return "Show your hand clearly as you gently grasp and release a light object. Keep the same object and phone position for comparisons.";
            case "object_transfer":
                return "Sit or stand safely. Show your hand as you move a light object between two nearby places. Use the same setup for comparisons.";
            case "vowel":
                return "Say a steady ‘ah’ at a comfortable volume for a few seconds. Breathe normally and do not force or prolong your breath. Record at least 2 seconds.";
            case "sentence":
                return "Read a short familiar sentence at your usual comfortable pace. Use the same sentence and language each time. Record at least 2 seconds.";
            case "natural":
                return "Talk comfortably about an ordinary part of your day for 10–20 seconds. Avoid sharing names or details you do not want in a saved recording.";
            default:
                return "Record at least 2 seconds and keep the same setup for comparisons. Stop whenever you feel tired, uncomfortable or unsteady.";
        }
    }

    private LinearLayout.LayoutParams spaced() {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(-1, -2);
        params.setMargins(0, dp(10), 0, dp(4));
        return params;
    }

    private TextView label(String text, int size, int color, boolean bold) {
        TextView view = new TextView(this);
        view.setText(text);
        view.setTextSize(size);
        view.setTextColor(color);
        view.setLineSpacing(dp(3), 1f);
        if (bold) view.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        return view;
    }

    private GradientDrawable panel() {
        GradientDrawable shape = new GradientDrawable();
        shape.setColor(PANEL);
        shape.setCornerRadius(dp(16));
        return shape;
    }

    private Button button(String text, boolean primary) {
        Button button = new Button(this);
        button.setText(text);
        button.setTextSize(16);
        button.setAllCaps(false);
        button.setTextColor(primary ? BACKGROUND : TEXT);
        button.setMinHeight(dp(52));
        button.setPadding(dp(12), dp(10), dp(12), dp(10));
        GradientDrawable shape = panel();
        shape.setColor(primary ? ACCENT : PANEL);
        button.setBackground(shape);
        return button;
    }
}
