package br.pucrs.tcc2.mvc.domain.io;

import br.pucrs.tcc2.mvc.common.exception.ExceptionMaker;
import br.pucrs.tcc2.mvc.domain.io.model.dto.IoDto;
import br.pucrs.tcc2.mvc.domain.io.model.input.AccessEventInput;
import br.pucrs.tcc2.mvc.domain.io.model.input.IoInput;
import br.pucrs.tcc2.mvc.domain.io.port.api.IoApiPort;
import br.pucrs.tcc2.mvc.domain.io.port.spi.IoSpiPort;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class IoService implements IoApiPort {
    private final IoSpiPort spiPort;

    public IoService(IoSpiPort spiPort) {
        this.spiPort = spiPort;
    }

    @Override
    @Transactional(isolation = Isolation.READ_COMMITTED)
    public IoDto execute(IoInput input) {
        spiPort.applyDatabaseDelay();
        var item = spiPort.findItemById(input.itemId())
                .orElseThrow(() -> ExceptionMaker.itemNotFound(input.itemId()));
        var category = spiPort.findCategoryById(item.categoryId())
                .orElseThrow(ExceptionMaker::inconsistentCatalog);
        var event = spiPort.appendEvent(new AccessEventInput(
                item.id(), input.runId(), input.requestId(), "ITEM_VIEW"));
        return new IoDto(item, category, event);
    }
}
