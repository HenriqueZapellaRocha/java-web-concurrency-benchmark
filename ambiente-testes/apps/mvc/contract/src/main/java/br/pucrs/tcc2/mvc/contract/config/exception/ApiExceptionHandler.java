package br.pucrs.tcc2.mvc.contract.config.exception;

import br.pucrs.tcc2.mvc.common.exception.ApplicationException;
import br.pucrs.tcc2.mvc.contract.config.exception.model.ErrorInfo;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DataAccessResourceFailureException;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ResponseEntity;
import org.springframework.transaction.CannotCreateTransactionException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler;

@RestControllerAdvice
public class ApiExceptionHandler extends ResponseEntityExceptionHandler {
    private static final Logger log = LoggerFactory.getLogger(ApiExceptionHandler.class);

    @ExceptionHandler(ApplicationException.class)
    public ResponseEntity<ErrorInfo> application(ApplicationException error) {
        HttpStatus status = switch (error.kind()) {
            case NOT_FOUND -> HttpStatus.NOT_FOUND;
            case CONFLICT -> HttpStatus.CONFLICT;
            case INCONSISTENT_CATALOG -> HttpStatus.INTERNAL_SERVER_ERROR;
        };
        if (status.is5xxServerError()) {
            log.error("I/O domain failure: {}", error.code());
        }
        return response(status, error.code(), error.getMessage(),
                status == HttpStatus.CONFLICT ? "Use a new requestId for a new access." : "Check the requested catalog item.");
    }

    @Override
    protected ResponseEntity<Object> handleExceptionInternal(Exception error, Object body,
            HttpHeaders headers, HttpStatusCode status, WebRequest request) {
        String code = status.value() == 400 ? "INVALID_REQUEST" : "HTTP_" + status.value();
        String message = status.value() == 400
                ? "The request must contain a positive itemId and valid runId/requestId UUIDs."
                : "The HTTP request could not be handled.";
        return new ResponseEntity<>(ErrorInfo.of(code, message, status.value(), "Review the HTTP request."), headers, status);
    }

    @ExceptionHandler({CannotCreateTransactionException.class, DataAccessResourceFailureException.class})
    public ResponseEntity<ErrorInfo> databaseUnavailable(Exception error) {
        log.error("I/O database unavailable", error);
        return response(HttpStatus.SERVICE_UNAVAILABLE, "DATABASE_UNAVAILABLE",
                "The database is unavailable.", "Check database availability before continuing the run.");
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<ErrorInfo> unexpected(Exception error) {
        log.error("Unexpected API failure", error);
        return response(HttpStatus.INTERNAL_SERVER_ERROR, "INTERNAL_ERROR",
                "The request could not be completed.", "Review the server logs before continuing the run.");
    }

    private ResponseEntity<ErrorInfo> response(HttpStatus status, String code, String message, String action) {
        return ResponseEntity.status(status).body(ErrorInfo.of(code, message, status.value(), action));
    }
}
