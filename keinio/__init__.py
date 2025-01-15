from typing import Callable, Generator, Generic, TypeVar, List
from .compat import Concatenate, ParamSpec, Self

P = ParamSpec('P')
T = TypeVar('T')
Receiver = Generator[None, bytes, None]
Coro = Generator[None, None, T]
DataCall = Callable[[bytes], None]

__all__ = ['Reader', 'Receiver', 'DataCall', 'Collector', 'Coro', 'IncompleteError']


class IncompleteError(Exception):
    partial: bytes


class Reader:
    _protocol: Coro[None]
    _push: DataCall

    def start(self, protocol: Coro[None]) -> None:
        self.buf = bytearray()
        self._protocol = protocol
        next(protocol)
        gen = self._process()
        next(gen)
        self._push = gen.send

    def push(self, data: bytes) -> None:
        try:
            self._push(data)
        except StopIteration:
            raise RuntimeError("Reader has received EOF already")

    @classmethod
    def protocol(cls, fn: Callable[Concatenate[Self, P], Coro[None]]) -> Callable[P, Self]:
        def inner(*args: P.args, **kwargs: P.kwargs) -> Reader:
            reader = cls()
            receiver = fn(reader, *args, **kwargs)
            reader.start(receiver)
            return reader
        return inner  # type: ignore[return-value]

    def read(self, size: int) -> Coro[bytes]:
        while len(self.buf) < size:
            yield

        rv = bytes(self.buf[:size])
        self.buf = self.buf[size:]
        return rv

    def readuntil(self, separator: bytes, include: bool=False, eof:bool=False) -> Coro[bytes]:
        # start = max(self._read_until_start - len(sep)+1, 0)
        start = 0
        while True:
            buf = self.buf
            idx = buf.find(separator, start)
            if idx >= 0:
                break

            start = max(len(buf) - len(separator) + 1, 0)
            try:
                yield
            except IncompleteError:
                if not eof:
                    raise
                self.buf = bytearray()
                if include:
                    return bytes(buf) + separator
                else:
                    return bytes(buf)

        sz = idx + len(separator)
        rvsize = sz if include else idx
        rv = bytes(buf[:rvsize])
        self.buf = buf[sz:]
        return rv

    def _process(self) -> Receiver:
        while True:
            data = yield
            if data:
                self.buf.extend(data)
                self._protocol.send(None)
            else:
                break

        if self.buf:
            error = IncompleteError()
            error.partial = bytes(self.buf)
            self._protocol.throw(error)
        else:
            self._protocol.close()

        yield


class Collector(Generic[T]):
    def __init__(self, proto: Callable[[Callable[[T], None]], Reader]):
        self.events: List[T] = []
        self.reader = proto(self.events.append)

    def send(self, data: bytes) -> List[T]:
        self.reader.push(data)
        if self.events:
            events = self.events[:]
            self.events.clear()
        else:
            events = []
        return events
