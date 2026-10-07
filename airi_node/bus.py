"""Small RESP2 client. Redis is transport; SQLite remains authoritative."""
import json
import socket
import threading
import time


class RedisError(RuntimeError):
    pass


class Bus:
    def __init__(self, host, port, password, timeout=1):
        self.host, self.port, self.password, self.timeout = host, port, password, timeout

    def command(self, *parts):
        def write(sock, args):
            values = [str(p).encode() if not isinstance(p, bytes) else p for p in args]
            sock.sendall(b'*'+str(len(values)).encode()+b'\r\n'+b''.join(
                b'$'+str(len(v)).encode()+b'\r\n'+v+b'\r\n' for v in values))
        def read(file, depth=0):
            if depth > 8:
                raise RedisError('Response nesting limit')
            line = file.readline(1000000)
            if not line.endswith(b'\r\n'):
                raise RedisError('Incomplete Redis response')
            kind, value = line[:1], line[1:-2]
            if kind == b'-':
                raise RedisError(value.decode(errors='replace'))
            if kind == b'+':
                return value.decode()
            if kind == b':':
                return int(value)
            n = int(value)
            if n == -1:
                return None
            if kind == b'$' and 0 <= n <= 2000000:
                raw = file.read(n+2)
                if len(raw) != n+2:
                    raise RedisError('Incomplete bulk response')
                return raw[:-2].decode()
            if kind == b'*' and 0 <= n <= 10000:
                return [read(file, depth+1) for _ in range(n)]
            raise RedisError('Invalid Redis response')
        with socket.create_connection((self.host,self.port),timeout=self.timeout) as sock:
            file = sock.makefile('rb')
            try:
                write(sock, ('AUTH',self.password)); read(file)
                write(sock, parts); return read(file)
            finally:
                file.close()

    def ping(self):
        return self.command('PING') == 'PONG'

    def publish(self, stream, value):
        return self.command('XADD',stream,'MAXLEN','~',10000,'*','data',json.dumps(value,separators=(',',':')))

    def next(self, stream, group, consumer, idle_ms=120000):
        try:
            self.command('XGROUP','CREATE',stream,group,'0','MKSTREAM')
        except RedisError as error:
            if 'BUSYGROUP' not in str(error):
                raise
        claimed = self.command('XAUTOCLAIM',stream,group,consumer,idle_ms,'0-0','COUNT',1)
        rows = claimed[1] if claimed else []
        if not rows:
            new = self.command('XREADGROUP','GROUP',group,consumer,'COUNT',1,'STREAMS',stream,'>')
            rows = new[0][1] if new else []
        return [(row[0],json.loads(dict(zip(row[1][::2],row[1][1::2]))['data'])) for row in rows]

    def ack(self, stream, group, identifier):
        return self.command('XACK',stream,group,identifier)


class Circuit:
    def __init__(self, threshold=5, window=120, cooldown=60):
        self.threshold,self.window,self.cooldown=threshold,window,cooldown
        self.failures={};self.opened={};self.trials=set();self.lock=threading.Lock()

    def allow(self,key,now=None):
        now=time.monotonic() if now is None else now
        with self.lock:
            if key not in self.opened:return True
            if now-self.opened[key]<self.cooldown or key in self.trials:return False
            self.trials.add(key);return True

    def result(self,key,ok,now=None):
        now=time.monotonic() if now is None else now
        with self.lock:
            trial=key in self.trials;self.trials.discard(key)
            if ok:
                self.failures.pop(key,None);self.opened.pop(key,None)
            else:
                recent=[t for t in self.failures.get(key,[]) if now-t<=self.window]+[now]
                self.failures[key]=recent
                if trial or len(recent)>=self.threshold:self.opened[key]=now

    def snapshot(self):
        with self.lock:return {k:'HALF_OPEN' if k in self.trials else 'OPEN' for k in self.opened}
