#include <iostream>
#include <nlohmann/json.hpp>

int main() {
    nlohmann::json j = {{"status", "offline-ok"}};
    std::cout << "cpp " << j.dump() << std::endl;
    return 0;
}
