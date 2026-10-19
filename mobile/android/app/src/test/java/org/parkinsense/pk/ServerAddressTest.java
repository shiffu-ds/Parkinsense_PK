package org.parkinsense.pk;

import org.junit.Test;
import static org.junit.Assert.*;

public final class ServerAddressTest {
    @Test public void privateWifiPreviewAcceptsNormalAddresses() {
        assertEquals("http://192.168.1.11:8767",ServerAddress.validate(" http://192.168.1.11:8767/ "));
        assertEquals("http://10.0.2.2:8767",ServerAddress.validate("http://10.0.2.2:8767"));
        assertEquals("http://172.31.255.254",ServerAddress.validate("http://172.31.255.254"));
        assertEquals("http://localhost:8767",ServerAddress.validate("http://LOCALHOST:8767"));
    }
    @Test public void publicOriginRequiresHttps() {
        assertEquals("https://api.example.com",ServerAddress.validate("https://API.Example.com/"));
        reject("http://api.example.com");reject("http://8.8.8.8");reject("http://172.32.1.1");
    }
    @Test public void credentialsAndQueryCannotBeEmbedded() {
        reject("https://user:password@api.example.com");reject("https://api.example.com?token=secret");
        reject("https://api.example.com#token");reject("https://api.example.com/sessions");
    }
    @Test public void ambiguousNumericHostsAndSchemesAreRejected() {
        reject("http://192.168.001.11");reject("http://0x7f000001");reject("http://127.1");
        reject("file:///tmp/token");reject("ftp://192.168.1.11");reject("https://api.example.com:0");
        reject("https://api.example.com:65536");reject("http://192.168.300.1");
    }
    @Test public void unrelatedLocalHostnamesCannotUseCleartext() {
        reject("http://patient.local");reject("http://localhost.example.com");reject("http://169.254.1.1");
    }
    private static void reject(String address) {
        try { ServerAddress.validate(address); fail("Unexpected accepted origin: "+address); }
        catch (IllegalArgumentException expected) { }
    }
}
