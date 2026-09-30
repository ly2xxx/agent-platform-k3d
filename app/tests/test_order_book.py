from app.order_book import Order, OrderBook, Side

def _bid(order_id: str, price: float, qty: int = 10) -> Order:
    return Order(order_id=order_id, side=Side.BID, price=price, quantity=qty)

def _ask(order_id: str, price: float, qty: int = 10) -> Order:
    return Order(order_id=order_id, side=Side.ASK, price=price, quantity=qty)

def test_empty_book_returns_none():  # spec behaviour 5
    book = OrderBook()
    assert book.best_bid() is None
    assert book.best_ask() is None

def test_best_bid_is_highest_price():  # spec behaviour 6
    book = OrderBook()
    for price in (100.0, 100.5, 99.5):
        book.add(_bid(f"b{price}", price))
    assert book.best_bid() is not None
    assert book.best_bid().price == 100.5

def test_best_ask_is_lowest_price():  # spec behaviour 7
    book = OrderBook()
    for price in (101.5, 101.0, 102.0):
        book.add(_ask(f"a{price}", price))
    assert book.best_ask() is not None
    assert book.best_ask().price == 101.0

def test_tie_at_best_bid_returns_first_added():  # spec behaviour 8
    book = OrderBook()
    book.add(_bid("first", 100.5))
    book.add(_bid("second", 100.5))
    assert book.best_bid() is not None
    assert book.best_bid().order_id == "first"

def test_tie_at_best_ask_returns_first_added():
    book = OrderBook()
    book.add(_ask("first", 101.0))
    book.add(_ask("second", 101.0))
    assert book.best_ask() is not None
    assert book.best_ask().order_id == "first"

def test_sides_are_independent():
    book = OrderBook()
    book.add(_bid("b", 99.0))
    book.add(_ask("a", 101.0))
    assert book.best_bid().price == 99.0
    assert book.best_ask().price == 101.0
