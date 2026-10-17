using Newtonsoft.Json;

Console.WriteLine("csharp " + JsonConvert.SerializeObject(new { status = "offline-ok" }));
