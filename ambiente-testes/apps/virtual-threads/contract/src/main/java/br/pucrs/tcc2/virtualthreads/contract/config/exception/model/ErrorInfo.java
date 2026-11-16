package br.pucrs.tcc2.virtualthreads.contract.config.exception.model;

import java.util.List;

public record ErrorInfo(List<ErrorSpec> errors) {
    public record ErrorSpec(String code, String message, List<Integer> httpStatusCodes,
                            List<String> suggestedUserActions, List<String> suggestedApplicationActions) {}

    public static ErrorInfo of(String code, String message, int status, String action) {
        return new ErrorInfo(List.of(new ErrorSpec(code, message, List.of(status),
                List.of(action), List.of(action))));
    }
}
