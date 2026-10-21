import http from 'node:http';
import {readFileSync} from 'node:fs';
import {calculate} from './calculate.js';
let good = 0, bad = 0;
const server = http.createServer((req, res) => {
    let status = 200, type = 'application/json', body;
    switch (req.url) {
        case '/health': case '/ready': body = JSON.stringify({status: 'ok'}); break;
        case '/version': body = JSON.stringify({revision: readFileSync('/app/revision', 'utf8').trim()}); break;
        case '/compute':
            if (process.env.FAIL_REQUESTS === 'true') { bad++; status = 500; } else good++;
            body = JSON.stringify({value: calculate(7)}); break;
        case '/metrics': type = 'text/plain'; body = `http_requests_total{status="200"} ${good}\nhttp_requests_total{status="500"} ${bad}\n`; break;
        case '/': type = 'text/html'; body = readFileSync(new URL('./public/index.html', import.meta.url)); break;
        default: status = 404; body = '{}';
    }
    console.log(JSON.stringify({event: 'request', status}));
    res.writeHead(status, {'Content-Type': type}); res.end(body);
});
server.listen(8080, '0.0.0.0');
process.on('SIGTERM', () => { server.close(() => process.exit(0)); setTimeout(() => process.exit(1), 25000).unref(); });
