use std::io::{Read, Write};
use std::net::TcpListener;
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::Duration;

static STOP: AtomicBool = AtomicBool::new(false);
extern "C" fn stop(_: i32) {
    STOP.store(true, Ordering::SeqCst);
}
extern "C" {
    fn signal(sig: i32, handler: extern "C" fn(i32)) -> usize;
}
fn calculate(value: i32) -> i32 {
    value * value
}
fn main() -> std::io::Result<()> {
    if std::env::args().any(|a| a == "--native") {
        println!("{}", calculate(7));
        return Ok(());
    }
    // 目标限定 Linux/amd64；处理 SIGTERM 后等待当前请求完成。
    unsafe {
        signal(15, stop);
        signal(2, stop);
    }
    let listener = TcpListener::bind("0.0.0.0:8080")?;
    listener.set_nonblocking(true)?;
    let (mut good, mut bad) = (0_u64, 0_u64);
    while !STOP.load(Ordering::SeqCst) {
        let mut stream = match listener.accept() {
            Ok((stream, _)) => stream,
            Err(e) if e.kind() == std::io::ErrorKind::WouldBlock => {
                std::thread::sleep(Duration::from_millis(50));
                continue;
            }
            Err(e) => return Err(e),
        };
        stream.set_read_timeout(Some(Duration::from_secs(2)))?;
        stream.set_write_timeout(Some(Duration::from_secs(2)))?;
        let mut buffer = [0; 4096];
        let count = match stream.read(&mut buffer) {
            Ok(count) => count,
            Err(_) => continue,
        };
        let request = String::from_utf8_lossy(&buffer[..count]);
        let path = request.split_whitespace().nth(1).unwrap_or("");
        let mut status = 200;
        let mut content_type = "application/json";
        let body = match path {
            "/health" | "/ready" => "{\"status\":\"ok\"}".to_owned(),
            "/version" => format!(
                "{{\"revision\":\"{}\"}}",
                std::fs::read_to_string("/app/revision")?.trim()
            ),
            "/compute" => {
                if std::env::var("FAIL_REQUESTS").unwrap_or_default() == "true" {
                    bad += 1;
                    status = 500;
                } else {
                    good += 1;
                }
                format!("{{\"value\":{}}}", calculate(7))
            }
            "/metrics" => {
                content_type = "text/plain";
                format!("http_requests_total{{status=\"200\"}} {good}\nhttp_requests_total{{status=\"500\"}} {bad}\n")
            }
            _ => {
                status = 404;
                "{}".to_owned()
            }
        };
        let response = format!(
            "HTTP/1.1 {status} Result\r\nContent-Type: {content_type}\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}",
            body.len()
        );
        if let Err(e) = stream.write_all(response.as_bytes()) {
            eprintln!("{{\"event\":\"client_write_failed\",\"kind\":\"{:?}\"}}", e.kind());
        }
        println!("{{\"event\":\"request\",\"status\":{status}}}");
    }
    Ok(())
}
#[cfg(test)]
mod tests {
    use super::calculate;
    #[test]
    fn signed_input() {
        assert_eq!(calculate(7), 49);
        assert_eq!(calculate(-7), 49);
        assert_eq!(calculate(0), 0);
    }
}
