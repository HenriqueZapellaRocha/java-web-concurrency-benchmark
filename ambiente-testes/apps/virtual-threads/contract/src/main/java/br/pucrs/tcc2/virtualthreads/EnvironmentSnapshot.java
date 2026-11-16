package br.pucrs.tcc2.virtualthreads;

/** Diagnóstico do ambiente; não executa um workload experimental. */
public record EnvironmentSnapshot(
        String model,
        String webStack,
        String javaVersion,
        String javaVendor,
        String springBootVersion,
        String threadName,
        boolean virtual,
        boolean nonBlocking,
        int availableProcessors) {

    public static EnvironmentSnapshot capture(String model, String webStack, String springBootVersion) {
        return capture(model, webStack, springBootVersion, false);
    }

    public static EnvironmentSnapshot capture(String model, String webStack, String springBootVersion,
                                              boolean nonBlocking) {
        Thread thread = Thread.currentThread();
        return new EnvironmentSnapshot(
                model,
                webStack,
                Runtime.version().toString(),
                System.getProperty("java.vendor"),
                springBootVersion,
                thread.getName(),
                thread.isVirtual(),
                nonBlocking,
                Runtime.getRuntime().availableProcessors());
    }
}
