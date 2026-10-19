package org.parkinsense.pk;

import android.content.Context;
import android.content.SharedPreferences;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;
import java.nio.charset.StandardCharsets;
import java.security.KeyStore;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

/** Tokens are encrypted with a non-exportable Android Keystore key; backups are disabled. */
public final class TokenStore {
    public static final String DEFAULT_SERVER = "http://192.168.1.11:8767";
    private static final String KEY_ALIAS = "parkinsense_patient_token_v1";
    private final SharedPreferences prefs;
    public TokenStore(Context context) {
        prefs = context.getApplicationContext().getSharedPreferences("patient_connection", Context.MODE_PRIVATE);
    }
    public synchronized String server() {
        try { return ServerAddress.validate(prefs.getString("server", DEFAULT_SERVER)); }
        catch (Exception e) { clear(); return DEFAULT_SERVER; }
    }
    public synchronized void setServer(String server) {
        String validated = ServerAddress.validate(server);
        prefs.edit().remove("token_cipher").remove("token_iv").putString("server", validated).commit();
    }
    private SecretKey key() throws Exception {
        KeyStore store = KeyStore.getInstance("AndroidKeyStore");
        store.load(null);
        if (store.containsAlias(KEY_ALIAS)) return (SecretKey) store.getKey(KEY_ALIAS, null);
        KeyGenerator generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore");
        generator.init(new KeyGenParameterSpec.Builder(KEY_ALIAS, KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setRandomizedEncryptionRequired(true).build());
        return generator.generateKey();
    }
    public synchronized void save(String token) throws Exception {
        if (token == null || !token.matches("[A-Za-z0-9._~-]{20,4096}")) throw new IllegalArgumentException("Invalid account token.");
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, key());
        byte[] encoded = cipher.doFinal(token.getBytes(StandardCharsets.UTF_8));
        boolean saved = prefs.edit().putString("token_cipher", Base64.encodeToString(encoded, Base64.NO_WRAP))
                .putString("token_iv", Base64.encodeToString(cipher.getIV(), Base64.NO_WRAP)).commit();
        if (!saved) throw new IllegalStateException("Unable to save sign-in on this phone.");
    }
    public synchronized String token() {
        String encoded = prefs.getString("token_cipher", null), iv = prefs.getString("token_iv", null);
        if (encoded == null || iv == null) return null;
        try {
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.DECRYPT_MODE, key(), new GCMParameterSpec(128, Base64.decode(iv, Base64.NO_WRAP)));
            String token = new String(cipher.doFinal(Base64.decode(encoded, Base64.NO_WRAP)), StandardCharsets.UTF_8);
            if (!token.matches("[A-Za-z0-9._~-]{20,4096}")) throw new IllegalArgumentException();
            return token;
        } catch (Exception e) { clear(); return null; }
    }
    public synchronized void clear() { prefs.edit().remove("token_cipher").remove("token_iv").commit(); }
}
