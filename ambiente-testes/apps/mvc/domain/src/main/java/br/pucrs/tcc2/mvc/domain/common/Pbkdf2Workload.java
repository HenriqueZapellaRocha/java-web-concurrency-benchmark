package br.pucrs.tcc2.mvc.domain.common;

import br.pucrs.tcc2.mvc.domain.cpu.model.dto.CpuDto;
import java.nio.charset.StandardCharsets;
import java.security.NoSuchAlgorithmException;
import java.security.spec.InvalidKeySpecException;
import java.util.HexFormat;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;

public final class Pbkdf2Workload {
    private static final char[] PASSWORD = "tcc2-login-password-v1".toCharArray();
    private static final byte[] SALT = "tcc2-pbkdf2-salt-v1".getBytes(StandardCharsets.UTF_8);
    private static final int KEY_LENGTH_BITS = 256;

    private Pbkdf2Workload() {
    }

    public static CpuDto execute(int iterations) {
        var specification = new PBEKeySpec(PASSWORD, SALT, iterations, KEY_LENGTH_BITS);
        try {
            byte[] derivedKey = factory().generateSecret(specification).getEncoded();
            return new CpuDto(iterations, HexFormat.of().formatHex(derivedKey));
        } catch (InvalidKeySpecException error) {
            throw new IllegalStateException("PBKDF2 key derivation failed", error);
        } finally {
            specification.clearPassword();
        }
    }

    private static SecretKeyFactory factory() {
        try {
            return SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256");
        } catch (NoSuchAlgorithmException error) {
            throw new IllegalStateException("PBKDF2WithHmacSHA256 is unavailable", error);
        }
    }
}
