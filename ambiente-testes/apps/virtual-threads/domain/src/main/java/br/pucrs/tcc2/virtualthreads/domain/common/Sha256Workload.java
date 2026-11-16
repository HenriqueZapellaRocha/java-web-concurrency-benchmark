package br.pucrs.tcc2.virtualthreads.domain.common;

import br.pucrs.tcc2.virtualthreads.domain.cpu.model.dto.CpuDto;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

public final class Sha256Workload {
    private static final byte[] INPUT = "tcc2-cpu-workload-v1".getBytes(StandardCharsets.UTF_8);
    private Sha256Workload() { }

    public static CpuDto execute(int iterations) {
        byte[] value = INPUT;
        MessageDigest sha256 = sha256();
        for (int index = 0; index < iterations; index++) value = sha256.digest(value);
        return new CpuDto(iterations, HexFormat.of().formatHex(value));
    }

    private static MessageDigest sha256() {
        try {
            return MessageDigest.getInstance("SHA-256");
        } catch (NoSuchAlgorithmException error) {
            throw new IllegalStateException("SHA-256 is unavailable", error);
        }
    }
}
