package org.parkinsense.pk;

import java.net.URI;
import java.net.URISyntaxException;
import java.util.Locale;

/** Server addresses cannot embed credentials or redirect bearer tokens to another origin. */
public final class ServerAddress {
    private ServerAddress() { }
    public static String validate(String input) {
        if (input == null || input.length() > 512) throw new IllegalArgumentException("Enter a valid server address.");
        try {
            URI uri = new URI(input.trim());
            String scheme = uri.getScheme() == null ? "" : uri.getScheme().toLowerCase(Locale.ROOT);
            String host = uri.getHost();
            if ((!scheme.equals("http") && !scheme.equals("https")) || host == null || host.trim().isEmpty()
                    || uri.getUserInfo() != null || uri.getRawQuery() != null || uri.getRawFragment() != null
                    || uri.getPort() == 0 || uri.getPort() > 65535) {
                throw new IllegalArgumentException("Use an HTTPS address, or HTTP on your private Wi-Fi network.");
            }
            if (scheme.equals("http") && !isPrivateHost(host)) {
                throw new IllegalArgumentException("Public servers require HTTPS. HTTP is allowed only on private Wi-Fi.");
            }
            String path = uri.getRawPath();
            if (path != null && !path.isEmpty() && !path.equals("/")) {
                throw new IllegalArgumentException("Enter the server origin only, without a path.");
            }
            String normalized = scheme + "://" + host.toLowerCase(Locale.ROOT) + (uri.getPort() == -1 ? "" : ":" + uri.getPort());
            return normalized;
        } catch (URISyntaxException e) {
            throw new IllegalArgumentException("Enter a valid server address, such as http://192.168.1.11:8767.");
        }
    }
    public static boolean isPrivateHost(String host) {
        String h = host.toLowerCase(Locale.ROOT);
        if (h.equals("localhost") || h.equals("[::1]") || h.equals("::1")) return true;
        String[] pieces = h.split("\\.", -1);
        if (pieces.length != 4) return false;
        int[] values = new int[4];
        for (int i = 0; i < 4; i++) {
            if (!pieces[i].matches("[0-9]{1,3}")) return false;
            values[i] = Integer.parseInt(pieces[i]);
            if (values[i] > 255 || (pieces[i].length() > 1 && pieces[i].startsWith("0"))) return false;
        }
        return values[0] == 10 || values[0] == 127 || (values[0] == 192 && values[1] == 168)
                || (values[0] == 172 && values[1] >= 16 && values[1] <= 31);
    }
}
