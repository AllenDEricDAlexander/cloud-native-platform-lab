package top.egon.cnpl;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class DemoApplication {
    private final AtomicLong good = new AtomicLong();
    private final AtomicLong bad = new AtomicLong();

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    static int calculate(int value) {
        return value * value;
    }

    @GetMapping({"/health", "/ready"})
    public Map<String, String> health() {
        return Map.of("status", "ok");
    }

    @GetMapping("/version")
    public Map<String, String> version() throws java.io.IOException {
        return Map.of("revision", Files.readString(Path.of("/app/revision")).trim());
    }

    @GetMapping("/compute")
    public ResponseEntity<Map<String, Object>> compute() {
        boolean failed = "true".equals(System.getenv("FAIL_REQUESTS"));
        (failed ? bad : good).incrementAndGet();
        return ResponseEntity.status(failed ? 500 : 200).body(Map.of("value", calculate(7), "status", failed ? "failed" : "ok"));
    }

    @GetMapping(value = "/metrics", produces = "text/plain")
    public String metrics() {
        return "http_requests_total{status=\"200\"} " + good.get() + "\nhttp_requests_total{status=\"500\"} " + bad.get() + "\n";
    }
}
