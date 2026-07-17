package io.dealhost.sdk;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

import java.util.List;
import org.junit.jupiter.api.Test;

class DealHostClientTest {
    @Test
    void hostingPayloadEscapesJsonControlCharacters() {
        String payload = DealHostClient.hostingPayload(
                "Tool",
                "tool",
                "First line\nSecond\t\"quoted\"\\slash\b\f\r\u0001",
                List.of(1, 2),
                true
        );

        assertEquals(
                "{\"name\":\"Tool\",\"slug\":\"tool\",\"description\":\"First line\\nSecond\\t\\\"quoted\\\"\\\\slash\\b\\f\\r\\u0001\",\"module_ids\":[1, 2],\"enabled\":true}",
                payload
        );
        assertFalse(payload.contains("\n"));
    }

    @Test
    void hostingPayloadDefaultsNullModuleIdsToAnEmptyArray() {
        String payload = DealHostClient.hostingPayload("Tool", "tool", "", null, false);

        assertEquals(
                "{\"name\":\"Tool\",\"slug\":\"tool\",\"description\":\"\",\"module_ids\":[],\"enabled\":false}",
                payload
        );
    }
}
