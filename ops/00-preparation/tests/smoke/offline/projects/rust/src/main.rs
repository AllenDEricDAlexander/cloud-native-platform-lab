fn main() {
    let mut buffer = itoa::Buffer::new();
    println!("rust itoa {} offline-ok", buffer.format(2026));
}
