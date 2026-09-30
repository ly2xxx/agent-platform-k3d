"""Heap-backed order book: bids in a max-heap, asks in a min-heap."""
import heapq
import itertools
from dataclasses import dataclass
from enum import Enum

class Side(str, Enum):
    BID = "bid"
    ASK = "ask"

@dataclass(frozen=True)
class Order:
    order_id: str
    side: Side
    price: float
    quantity: int

class OrderBook:
    def __init__(self) -> None:
        # Entries: bids (-price, seq, order) -> max-heap by price, FIFO on ties.
        # Entries: asks (price, seq, order) -> min-heap by price, FIFO on ties.
        self._bids: list[tuple[float, int, Order]] = []
        self._asks: list[tuple[float, int, Order]] = []
        self._counter = itertools.count()

    def add(self, order: Order) -> None:
        seq = next(self._counter)
        if order.side is Side.BID:
            heapq.heappush(self._bids, (-order.price, seq, order))
        else:
            heapq.heappush(self._asks, (order.price, seq, order))

    def best_bid(self) -> Order | None:
        return self._bids[0][2] if self._bids else None

    def best_ask(self) -> Order | None:
        return self._asks[0][2] if self._asks else None
