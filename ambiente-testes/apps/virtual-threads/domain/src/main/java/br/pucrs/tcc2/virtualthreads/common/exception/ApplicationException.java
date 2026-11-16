package br.pucrs.tcc2.virtualthreads.common.exception;

public class ApplicationException extends RuntimeException {
    public enum Kind { NOT_FOUND, CONFLICT, INCONSISTENT_CATALOG }

    private final Kind kind;
    private final String code;

    public ApplicationException(Kind kind, String code, String message) {
        super(message);
        this.kind = kind;
        this.code = code;
    }

    public Kind kind() { return kind; }
    public String code() { return code; }
}
