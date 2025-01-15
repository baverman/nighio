import functools
from typing import Callable, TYPE_CHECKING, Any, Generator, Optional, Tuple, Generic, TypeVar, List
from .compat import Concatenate, ParamSpec

P = ParamSpec('P')
T = TypeVar('T')
Receiver = Generator[None, bytes, None]
Coro = Generator[None, None, T]
DataCall = Callable[[bytes], None]
SizeResult = Tuple[int, bytes]

__all__ = ['Reader', 'protocol', 'Receiver', 'DataCall', 'Collector', 'SizeResult', 'Coro', 'IncompleteError']


class IncompleteError(Exception):
    partial: bytes


def safe_data_fn(fn: DataCall) -> DataCall:
    @functools.wraps(fn)
    def inner(data: bytes) -> None:
        try:
            fn(data)
        except StopIteration:
            pass
    return inner


class Reader:
    def start(self, receiver: Coro[None]) -> DataCall:
        self.buf = bytearray()
        self._receiver = receiver
        next(receiver)
        gen = self._process()
        next(gen)
        return safe_data_fn(gen.send)

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
                self._receiver.send(None)
            else:
                break

        if self.buf:
            error = IncompleteError()
            error.partial = bytes(self.buf)
            self._receiver.throw(error)
        else:
            self._receiver.close()


def protocol(cls: type[Reader]=Reader) -> Callable[[Callable[Concatenate[Reader, P], Coro[None]]], Callable[P, DataCall]]:
    def decorator(fn: Callable[Concatenate[Reader, P], Coro[None]]) -> Callable[P, DataCall]:
        def inner(*args: P.args, **kwargs: P.kwargs) -> DataCall:
            reader = cls()
            receiver = fn(reader, *args, **kwargs)
            return reader.start(receiver)
        return inner
    return decorator


class Collector(Generic[T]):
    def __init__(self, proto: Callable[[Callable[[T], None]], DataCall]):
        self.events: List[T] = []
        self.proto = proto(self.events.append)

    def send(self, data: bytes) -> List[T]:
        self.proto(data)
        if self.events:
            events = self.events[:]
            self.events.clear()
        else:
            events = []
        return events
