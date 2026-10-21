package top.egon.cnpl;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class DemoApplicationTest {
    @Test
    void calculatesPositiveAndNegativeInputs() {
        assertEquals(49, DemoApplication.calculate(7));
        assertEquals(49, DemoApplication.calculate(-7));
        assertEquals(0, DemoApplication.calculate(0));
    }
}
