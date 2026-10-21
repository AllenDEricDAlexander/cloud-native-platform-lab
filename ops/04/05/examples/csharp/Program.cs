using System.Threading;

static int Calculate(int value) => value * value;
if (args.Contains("--self-test"))
{
    if (Calculate(7) != 49 || Calculate(-7) != 49 || Calculate(0) != 0) throw new InvalidOperationException("Kernel test failed");
    return;
}
var builder = WebApplication.CreateBuilder(args);
builder.Logging.ClearProviders();
builder.Logging.AddJsonConsole();
builder.WebHost.UseUrls("http://0.0.0.0:8080");
var app = builder.Build();
long good = 0, bad = 0;
app.MapGet("/health", () => new { status = "ok" });
app.MapGet("/ready", () => new { status = "ok" });
app.MapGet("/version", () => new { revision = File.ReadAllText("/app/revision").Trim() });
app.MapGet("/compute", () =>
{
    bool failed = Environment.GetEnvironmentVariable("FAIL_REQUESTS") == "true";
    if (failed) Interlocked.Increment(ref bad); else Interlocked.Increment(ref good);
    return Results.Json(new { value = Calculate(7) }, statusCode: failed ? 500 : 200);
});
app.MapGet("/metrics", () => Results.Text($"http_requests_total{{status=\"200\"}} {Interlocked.Read(ref good)}\nhttp_requests_total{{status=\"500\"}} {Interlocked.Read(ref bad)}\n", "text/plain"));
app.Run();
