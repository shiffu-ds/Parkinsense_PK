package org.parkinsense.pk;

import android.os.Handler;
import android.os.Looper;
import org.json.JSONArray;
import org.json.JSONObject;
import org.json.JSONTokener;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class ApiClient {
    public interface Callback { void success(Object response); void failure(int status, String message); }
    private final TokenStore store;
    private final Handler main = new Handler(Looper.getMainLooper());
    private final ExecutorService executor = Executors.newFixedThreadPool(2);
    private final Set<HttpURLConnection> connections = ConcurrentHashMap.newKeySet();
    private volatile long generation;
    private volatile boolean closed;
    public ApiClient(TokenStore store) { this.store = store; }
    public synchronized void invalidate() {
        generation++;
        for (HttpURLConnection connection : connections) connection.disconnect();
        connections.clear();
    }
    public synchronized void close() { closed = true; invalidate(); executor.shutdownNow(); }
    public void get(String path, Callback callback) { request("GET", path, null, null, null, null, callback); }
    public void post(String path, JSONObject data, Callback callback) { request("POST", path, data, null, null, null, callback); }
    public void upload(String path, File file, String mime, String task, Callback callback) {
        request("POST", path, null, file, mime, task, callback);
    }
    private void request(String method, String path, JSONObject json, File file, String mime, String task, Callback callback) {
        if (!path.startsWith("/") || path.contains("..") || path.contains("://")) throw new IllegalArgumentException("Invalid API path.");
        final long epoch = generation;
        final String origin;
        final String token;
        synchronized (store) { origin = store.server(); token = store.token(); }
        if (closed) return;
        executor.execute(() -> {
            HttpURLConnection connection = null;
            try {
                if (closed || generation != epoch) return;
                connection = (HttpURLConnection) new URL(origin + path).openConnection();
                connections.add(connection);
                connection.setInstanceFollowRedirects(false);
                connection.setConnectTimeout(12000);
                connection.setReadTimeout(file == null ? 30000 : 180000);
                connection.setRequestMethod(method);
                connection.setRequestProperty("Accept", "application/json");
                if (token != null) connection.setRequestProperty("Authorization", "Bearer " + token);
                if (file != null) {
                    if (!file.isFile() || file.length() < 1 || file.length() > 100L * 1024 * 1024) throw new IllegalArgumentException("The recording is missing or exceeds 100 MB.");
                    if (!mime.equals("audio/wav") && !mime.equals("video/mp4")) throw new IllegalArgumentException("Use a WAV or MP4 recording.");
                    if (task == null || !task.matches("[a-z_]{1,40}")) throw new IllegalArgumentException("Choose a recording task.");
                    String boundary = "ParkinSense" + UUID.randomUUID().toString().replace("-", "");
                    byte[] prefix = ("--" + boundary + "\r\nContent-Disposition: form-data; name=\"task\"\r\n\r\n" + task + "\r\n--" + boundary
                            + "\r\nContent-Disposition: form-data; name=\"file\"; filename=\"recording." + (mime.equals("audio/wav") ? "wav" : "mp4") + "\"\r\nContent-Type: " + mime + "\r\n\r\n").getBytes(StandardCharsets.UTF_8);
                    byte[] suffix = ("\r\n--" + boundary + "--\r\n").getBytes(StandardCharsets.UTF_8);
                    connection.setDoOutput(true);
                    connection.setRequestProperty("Content-Type", "multipart/form-data; boundary=" + boundary);
                    connection.setFixedLengthStreamingMode(prefix.length + file.length() + suffix.length);
                    try (OutputStream out = connection.getOutputStream(); FileInputStream in = new FileInputStream(file)) {
                        out.write(prefix); byte[] buffer = new byte[32768]; int size;
                        while ((size = in.read(buffer)) != -1) {
                            if (closed || generation != epoch || Thread.currentThread().isInterrupted()) return;
                            out.write(buffer, 0, size);
                        }
                        out.write(suffix);
                    }
                } else if (!method.equals("GET")) {
                    byte[] body = (json == null ? "{}" : json.toString()).getBytes(StandardCharsets.UTF_8);
                    connection.setDoOutput(true);
                    connection.setRequestProperty("Content-Type", "application/json; charset=utf-8");
                    connection.setFixedLengthStreamingMode(body.length);
                    try (OutputStream out = connection.getOutputStream()) { out.write(body); }
                }
                int status = connection.getResponseCode();
                String body;
                try (InputStream in = status < 400 ? connection.getInputStream() : connection.getErrorStream()) {
                    body = readBounded(in);
                }
                if (status >= 200 && status < 300) {
                    Object response = body.trim().isEmpty() ? new JSONObject() : new JSONTokener(body).nextValue();
                    if (!(response instanceof JSONObject) && !(response instanceof JSONArray)) throw new IllegalArgumentException("The server returned an invalid response.");
                    dispatch(epoch, () -> callback.success(response));
                } else {
                    String message = status == 401 ? (path.equals("/auth/login") ? "Email or password is incorrect, or the account is inactive." : "Your sign-in expired. Please log in again.") : status == 403 ? "This action needs account access and active personal monitoring consent. Check Account > Personal monitoring consent." : status == 429 ? "Please wait a moment before trying again." : status >= 500 ? "The server could not finish this request. Please retry." : "The server rejected this request.";
                    if (status >= 400 && status < 500 && status != 401 && status != 403) {
                        try { String detail = new JSONObject(body).optString("detail", ""); if (!detail.trim().isEmpty() && detail.length() <= 240) message = detail; } catch (Exception ignored) { }
                    }
                    final String safe = message;
                    dispatch(epoch, () -> callback.failure(status, safe));
                }
            } catch (Exception e) {
                String message = e instanceof IllegalArgumentException ? e.getMessage() : "Cannot connect. Check the server address, laptop service, and Wi-Fi, then retry.";
                dispatch(epoch, () -> callback.failure(0, message == null ? "Connection failed." : message));
            } finally {
                if (connection != null) { connections.remove(connection); connection.disconnect(); }
            }
        });
    }
    private void dispatch(long epoch, Runnable callback) { main.post(() -> { if (!closed && epoch == generation) callback.run(); }); }
    private static String readBounded(InputStream in) throws Exception {
        if (in == null) return "";
        try (ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[8192]; int length;
            while ((length = in.read(buffer)) != -1) { if (out.size() + length > 2 * 1024 * 1024) throw new IllegalArgumentException("The server response is too large."); out.write(buffer, 0, length); }
            return out.toString(StandardCharsets.UTF_8.name());
        }
    }
}
