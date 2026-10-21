import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;

/** Standard JDK client; run inside an explicitly selected Dapr application Pod. */
public final class DaprClient {
    public static void main(String[] args) throws Exception {
        if (args.length < 1 || args.length > 2 || !args[0].matches("[A-Za-z0-9-]{1,64}")) {
            throw new IllegalArgumentException("DaprClient <event-id> [private-token-file]");
        }
        String id = args[0];
        String token = args.length == 2 ? Files.readString(Path.of(args[1])).strip() : null;
        HttpClient client = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(5)).build();
        String value = "{\"id\":\"" + id + "\",\"value\":\"cnpl06\"}";
        send(client, "state/lab-state", "[{\"key\":\"" + id + "\",\"value\":" + value + "}]", token);
        String recovered = send(client, "state/lab-state/" + id, null, token);
        String compact = recovered.replaceAll("\\s+", "");
        String reversed = "{\"value\":\"cnpl06\",\"id\":\"" + id + "\"}";
        if (!compact.equals(value) && !compact.equals(reversed)) {
            throw new IllegalStateException("State read-back mismatch");
        }
        send(client, "publish/lab-pubsub/orders", value, token);
        System.out.println("{\"id\":\"" + id + "\",\"publish_accepted\":true,\"effect_verified\":false}");
    }

    private static String send(HttpClient client, String path, String body, String token) throws Exception {
        HttpRequest.Builder request = HttpRequest.newBuilder(URI.create("http://127.0.0.1:3500/v1.0/" + path))
                .timeout(Duration.ofSeconds(10)).header("Content-Type", "application/json");
        if (token != null) {
            request.header("dapr-api-token", token);
        }
        if (body == null) {
            request.GET();
        } else {
            request.POST(HttpRequest.BodyPublishers.ofString(body));
        }
        HttpResponse<String> response = client.send(request.build(), HttpResponse.BodyHandlers.ofString());
        if (response.statusCode() < 200 || response.statusCode() >= 300) {
            throw new IllegalStateException("Dapr HTTP status " + response.statusCode());
        }
        return response.body();
    }
}
