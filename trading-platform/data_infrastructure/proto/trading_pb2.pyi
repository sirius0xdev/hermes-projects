from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class OrderSide(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    ORDER_SIDE_UNSPECIFIED: _ClassVar[OrderSide]
    BUY: _ClassVar[OrderSide]
    SELL: _ClassVar[OrderSide]

class OrderType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    ORDER_TYPE_UNSPECIFIED: _ClassVar[OrderType]
    MARKET: _ClassVar[OrderType]
    LIMIT: _ClassVar[OrderType]
    STOP: _ClassVar[OrderType]
    STOP_MARKET: _ClassVar[OrderType]

class TimeInForce(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    TIME_IN_FORCE_UNSPECIFIED: _ClassVar[TimeInForce]
    GTC: _ClassVar[TimeInForce]
    IOC: _ClassVar[TimeInForce]
    FOK: _ClassVar[TimeInForce]

class OrderStatus(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    ORDER_STATUS_UNSPECIFIED: _ClassVar[OrderStatus]
    PENDING: _ClassVar[OrderStatus]
    SUBMITTED: _ClassVar[OrderStatus]
    PARTIALLY_FILLED: _ClassVar[OrderStatus]
    FILLED: _ClassVar[OrderStatus]
    CANCELLED: _ClassVar[OrderStatus]
    REJECTED: _ClassVar[OrderStatus]
    EXPIRED: _ClassVar[OrderStatus]

class PositionSide(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    POSITION_SIDE_UNSPECIFIED: _ClassVar[PositionSide]
    LONG: _ClassVar[PositionSide]
    SHORT: _ClassVar[PositionSide]
    FLAT: _ClassVar[PositionSide]

class PnLType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    PNL_TYPE_UNSPECIFIED: _ClassVar[PnLType]
    REALIZED: _ClassVar[PnLType]
    MARK_TO_MARKET: _ClassVar[PnLType]

class UpdateType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    UPDATE_TYPE_UNSPECIFIED: _ClassVar[UpdateType]
    SNAPSHOT: _ClassVar[UpdateType]
    DELTA: _ClassVar[UpdateType]

class CommandType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    COMMAND_TYPE_UNSPECIFIED: _ClassVar[CommandType]
    PAUSE_INGESTION: _ClassVar[CommandType]
    RESUME_INGESTION: _ClassVar[CommandType]
    FORCE_REPLAY: _ClassVar[CommandType]
    SHUTDOWN: _ClassVar[CommandType]
ORDER_SIDE_UNSPECIFIED: OrderSide
BUY: OrderSide
SELL: OrderSide
ORDER_TYPE_UNSPECIFIED: OrderType
MARKET: OrderType
LIMIT: OrderType
STOP: OrderType
STOP_MARKET: OrderType
TIME_IN_FORCE_UNSPECIFIED: TimeInForce
GTC: TimeInForce
IOC: TimeInForce
FOK: TimeInForce
ORDER_STATUS_UNSPECIFIED: OrderStatus
PENDING: OrderStatus
SUBMITTED: OrderStatus
PARTIALLY_FILLED: OrderStatus
FILLED: OrderStatus
CANCELLED: OrderStatus
REJECTED: OrderStatus
EXPIRED: OrderStatus
POSITION_SIDE_UNSPECIFIED: PositionSide
LONG: PositionSide
SHORT: PositionSide
FLAT: PositionSide
PNL_TYPE_UNSPECIFIED: PnLType
REALIZED: PnLType
MARK_TO_MARKET: PnLType
UPDATE_TYPE_UNSPECIFIED: UpdateType
SNAPSHOT: UpdateType
DELTA: UpdateType
COMMAND_TYPE_UNSPECIFIED: CommandType
PAUSE_INGESTION: CommandType
RESUME_INGESTION: CommandType
FORCE_REPLAY: CommandType
SHUTDOWN: CommandType

class TickData(_message.Message):
    __slots__ = ("symbol", "price", "quantity", "timestamp_us", "source", "is_buyer_maker", "trade_id")
    SYMBOL_FIELD_NUMBER: _ClassVar[int]
    PRICE_FIELD_NUMBER: _ClassVar[int]
    QUANTITY_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_US_FIELD_NUMBER: _ClassVar[int]
    SOURCE_FIELD_NUMBER: _ClassVar[int]
    IS_BUYER_MAKER_FIELD_NUMBER: _ClassVar[int]
    TRADE_ID_FIELD_NUMBER: _ClassVar[int]
    symbol: str
    price: float
    quantity: float
    timestamp_us: int
    source: str
    is_buyer_maker: bool
    trade_id: str
    def __init__(self, symbol: _Optional[str] = ..., price: _Optional[float] = ..., quantity: _Optional[float] = ..., timestamp_us: _Optional[int] = ..., source: _Optional[str] = ..., is_buyer_maker: bool = ..., trade_id: _Optional[str] = ...) -> None: ...

class BBOQuote(_message.Message):
    __slots__ = ("symbol", "bid_price", "bid_size", "ask_price", "ask_size", "timestamp_us", "source")
    SYMBOL_FIELD_NUMBER: _ClassVar[int]
    BID_PRICE_FIELD_NUMBER: _ClassVar[int]
    BID_SIZE_FIELD_NUMBER: _ClassVar[int]
    ASK_PRICE_FIELD_NUMBER: _ClassVar[int]
    ASK_SIZE_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_US_FIELD_NUMBER: _ClassVar[int]
    SOURCE_FIELD_NUMBER: _ClassVar[int]
    symbol: str
    bid_price: float
    bid_size: float
    ask_price: float
    ask_size: float
    timestamp_us: int
    source: str
    def __init__(self, symbol: _Optional[str] = ..., bid_price: _Optional[float] = ..., bid_size: _Optional[float] = ..., ask_price: _Optional[float] = ..., ask_size: _Optional[float] = ..., timestamp_us: _Optional[int] = ..., source: _Optional[str] = ...) -> None: ...

class OrderBookLevel(_message.Message):
    __slots__ = ("price", "quantity", "order_count")
    PRICE_FIELD_NUMBER: _ClassVar[int]
    QUANTITY_FIELD_NUMBER: _ClassVar[int]
    ORDER_COUNT_FIELD_NUMBER: _ClassVar[int]
    price: float
    quantity: float
    order_count: int
    def __init__(self, price: _Optional[float] = ..., quantity: _Optional[float] = ..., order_count: _Optional[int] = ...) -> None: ...

class OrderBookUpdate(_message.Message):
    __slots__ = ("symbol", "sequence", "bids", "asks", "timestamp_us", "source", "type")
    SYMBOL_FIELD_NUMBER: _ClassVar[int]
    SEQUENCE_FIELD_NUMBER: _ClassVar[int]
    BIDS_FIELD_NUMBER: _ClassVar[int]
    ASKS_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_US_FIELD_NUMBER: _ClassVar[int]
    SOURCE_FIELD_NUMBER: _ClassVar[int]
    TYPE_FIELD_NUMBER: _ClassVar[int]
    symbol: str
    sequence: int
    bids: _containers.RepeatedCompositeFieldContainer[OrderBookLevel]
    asks: _containers.RepeatedCompositeFieldContainer[OrderBookLevel]
    timestamp_us: int
    source: str
    type: UpdateType
    def __init__(self, symbol: _Optional[str] = ..., sequence: _Optional[int] = ..., bids: _Optional[_Iterable[_Union[OrderBookLevel, _Mapping]]] = ..., asks: _Optional[_Iterable[_Union[OrderBookLevel, _Mapping]]] = ..., timestamp_us: _Optional[int] = ..., source: _Optional[str] = ..., type: _Optional[_Union[UpdateType, str]] = ...) -> None: ...

class CandleData(_message.Message):
    __slots__ = ("symbol", "interval", "open", "high", "low", "close", "volume", "quote_volume", "trade_count", "open_time_us", "close_time_us")
    SYMBOL_FIELD_NUMBER: _ClassVar[int]
    INTERVAL_FIELD_NUMBER: _ClassVar[int]
    OPEN_FIELD_NUMBER: _ClassVar[int]
    HIGH_FIELD_NUMBER: _ClassVar[int]
    LOW_FIELD_NUMBER: _ClassVar[int]
    CLOSE_FIELD_NUMBER: _ClassVar[int]
    VOLUME_FIELD_NUMBER: _ClassVar[int]
    QUOTE_VOLUME_FIELD_NUMBER: _ClassVar[int]
    TRADE_COUNT_FIELD_NUMBER: _ClassVar[int]
    OPEN_TIME_US_FIELD_NUMBER: _ClassVar[int]
    CLOSE_TIME_US_FIELD_NUMBER: _ClassVar[int]
    symbol: str
    interval: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    quote_volume: float
    trade_count: int
    open_time_us: int
    close_time_us: int
    def __init__(self, symbol: _Optional[str] = ..., interval: _Optional[str] = ..., open: _Optional[float] = ..., high: _Optional[float] = ..., low: _Optional[float] = ..., close: _Optional[float] = ..., volume: _Optional[float] = ..., quote_volume: _Optional[float] = ..., trade_count: _Optional[int] = ..., open_time_us: _Optional[int] = ..., close_time_us: _Optional[int] = ...) -> None: ...

class TickBatch(_message.Message):
    __slots__ = ("symbol", "source", "ticks")
    SYMBOL_FIELD_NUMBER: _ClassVar[int]
    SOURCE_FIELD_NUMBER: _ClassVar[int]
    TICKS_FIELD_NUMBER: _ClassVar[int]
    symbol: str
    source: str
    ticks: _containers.RepeatedCompositeFieldContainer[TickData]
    def __init__(self, symbol: _Optional[str] = ..., source: _Optional[str] = ..., ticks: _Optional[_Iterable[_Union[TickData, _Mapping]]] = ...) -> None: ...

class NewOrder(_message.Message):
    __slots__ = ("client_order_id", "wallet_address", "chain", "symbol", "side", "order_type", "quantity", "price", "stop_price", "reduce_only", "time_in_force", "submitted_at_us")
    CLIENT_ORDER_ID_FIELD_NUMBER: _ClassVar[int]
    WALLET_ADDRESS_FIELD_NUMBER: _ClassVar[int]
    CHAIN_FIELD_NUMBER: _ClassVar[int]
    SYMBOL_FIELD_NUMBER: _ClassVar[int]
    SIDE_FIELD_NUMBER: _ClassVar[int]
    ORDER_TYPE_FIELD_NUMBER: _ClassVar[int]
    QUANTITY_FIELD_NUMBER: _ClassVar[int]
    PRICE_FIELD_NUMBER: _ClassVar[int]
    STOP_PRICE_FIELD_NUMBER: _ClassVar[int]
    REDUCE_ONLY_FIELD_NUMBER: _ClassVar[int]
    TIME_IN_FORCE_FIELD_NUMBER: _ClassVar[int]
    SUBMITTED_AT_US_FIELD_NUMBER: _ClassVar[int]
    client_order_id: str
    wallet_address: str
    chain: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    price: float
    stop_price: float
    reduce_only: bool
    time_in_force: TimeInForce
    submitted_at_us: int
    def __init__(self, client_order_id: _Optional[str] = ..., wallet_address: _Optional[str] = ..., chain: _Optional[str] = ..., symbol: _Optional[str] = ..., side: _Optional[_Union[OrderSide, str]] = ..., order_type: _Optional[_Union[OrderType, str]] = ..., quantity: _Optional[float] = ..., price: _Optional[float] = ..., stop_price: _Optional[float] = ..., reduce_only: bool = ..., time_in_force: _Optional[_Union[TimeInForce, str]] = ..., submitted_at_us: _Optional[int] = ...) -> None: ...

class FillReport(_message.Message):
    __slots__ = ("fill_id", "client_order_id", "order_id", "symbol", "side", "fill_price", "fill_quantity", "fee", "fee_currency", "is_maker", "external_fill_id", "external_order_id", "filled_at_us")
    FILL_ID_FIELD_NUMBER: _ClassVar[int]
    CLIENT_ORDER_ID_FIELD_NUMBER: _ClassVar[int]
    ORDER_ID_FIELD_NUMBER: _ClassVar[int]
    SYMBOL_FIELD_NUMBER: _ClassVar[int]
    SIDE_FIELD_NUMBER: _ClassVar[int]
    FILL_PRICE_FIELD_NUMBER: _ClassVar[int]
    FILL_QUANTITY_FIELD_NUMBER: _ClassVar[int]
    FEE_FIELD_NUMBER: _ClassVar[int]
    FEE_CURRENCY_FIELD_NUMBER: _ClassVar[int]
    IS_MAKER_FIELD_NUMBER: _ClassVar[int]
    EXTERNAL_FILL_ID_FIELD_NUMBER: _ClassVar[int]
    EXTERNAL_ORDER_ID_FIELD_NUMBER: _ClassVar[int]
    FILLED_AT_US_FIELD_NUMBER: _ClassVar[int]
    fill_id: str
    client_order_id: str
    order_id: str
    symbol: str
    side: OrderSide
    fill_price: float
    fill_quantity: float
    fee: float
    fee_currency: str
    is_maker: bool
    external_fill_id: str
    external_order_id: str
    filled_at_us: int
    def __init__(self, fill_id: _Optional[str] = ..., client_order_id: _Optional[str] = ..., order_id: _Optional[str] = ..., symbol: _Optional[str] = ..., side: _Optional[_Union[OrderSide, str]] = ..., fill_price: _Optional[float] = ..., fill_quantity: _Optional[float] = ..., fee: _Optional[float] = ..., fee_currency: _Optional[str] = ..., is_maker: bool = ..., external_fill_id: _Optional[str] = ..., external_order_id: _Optional[str] = ..., filled_at_us: _Optional[int] = ...) -> None: ...

class OrderStatusUpdate(_message.Message):
    __slots__ = ("client_order_id", "external_order_id", "status", "fill_price", "fill_quantity", "error_message", "updated_at_us")
    CLIENT_ORDER_ID_FIELD_NUMBER: _ClassVar[int]
    EXTERNAL_ORDER_ID_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    FILL_PRICE_FIELD_NUMBER: _ClassVar[int]
    FILL_QUANTITY_FIELD_NUMBER: _ClassVar[int]
    ERROR_MESSAGE_FIELD_NUMBER: _ClassVar[int]
    UPDATED_AT_US_FIELD_NUMBER: _ClassVar[int]
    client_order_id: str
    external_order_id: str
    status: OrderStatus
    fill_price: float
    fill_quantity: float
    error_message: str
    updated_at_us: int
    def __init__(self, client_order_id: _Optional[str] = ..., external_order_id: _Optional[str] = ..., status: _Optional[_Union[OrderStatus, str]] = ..., fill_price: _Optional[float] = ..., fill_quantity: _Optional[float] = ..., error_message: _Optional[str] = ..., updated_at_us: _Optional[int] = ...) -> None: ...

class PositionUpdate(_message.Message):
    __slots__ = ("wallet_address", "chain", "symbol", "side", "size", "entry_price", "unrealized_pnl", "mark_price", "liquidation_price", "leverage", "margin", "is_open", "updated_at_us")
    WALLET_ADDRESS_FIELD_NUMBER: _ClassVar[int]
    CHAIN_FIELD_NUMBER: _ClassVar[int]
    SYMBOL_FIELD_NUMBER: _ClassVar[int]
    SIDE_FIELD_NUMBER: _ClassVar[int]
    SIZE_FIELD_NUMBER: _ClassVar[int]
    ENTRY_PRICE_FIELD_NUMBER: _ClassVar[int]
    UNREALIZED_PNL_FIELD_NUMBER: _ClassVar[int]
    MARK_PRICE_FIELD_NUMBER: _ClassVar[int]
    LIQUIDATION_PRICE_FIELD_NUMBER: _ClassVar[int]
    LEVERAGE_FIELD_NUMBER: _ClassVar[int]
    MARGIN_FIELD_NUMBER: _ClassVar[int]
    IS_OPEN_FIELD_NUMBER: _ClassVar[int]
    UPDATED_AT_US_FIELD_NUMBER: _ClassVar[int]
    wallet_address: str
    chain: str
    symbol: str
    side: PositionSide
    size: float
    entry_price: float
    unrealized_pnl: float
    mark_price: float
    liquidation_price: float
    leverage: float
    margin: float
    is_open: bool
    updated_at_us: int
    def __init__(self, wallet_address: _Optional[str] = ..., chain: _Optional[str] = ..., symbol: _Optional[str] = ..., side: _Optional[_Union[PositionSide, str]] = ..., size: _Optional[float] = ..., entry_price: _Optional[float] = ..., unrealized_pnl: _Optional[float] = ..., mark_price: _Optional[float] = ..., liquidation_price: _Optional[float] = ..., leverage: _Optional[float] = ..., margin: _Optional[float] = ..., is_open: bool = ..., updated_at_us: _Optional[int] = ...) -> None: ...

class PnLEvent(_message.Message):
    __slots__ = ("wallet_address", "chain", "symbol", "pnl_type", "realized_pnl", "unrealized_pnl", "fees", "currency", "event_time_us")
    WALLET_ADDRESS_FIELD_NUMBER: _ClassVar[int]
    CHAIN_FIELD_NUMBER: _ClassVar[int]
    SYMBOL_FIELD_NUMBER: _ClassVar[int]
    PNL_TYPE_FIELD_NUMBER: _ClassVar[int]
    REALIZED_PNL_FIELD_NUMBER: _ClassVar[int]
    UNREALIZED_PNL_FIELD_NUMBER: _ClassVar[int]
    FEES_FIELD_NUMBER: _ClassVar[int]
    CURRENCY_FIELD_NUMBER: _ClassVar[int]
    EVENT_TIME_US_FIELD_NUMBER: _ClassVar[int]
    wallet_address: str
    chain: str
    symbol: str
    pnl_type: PnLType
    realized_pnl: float
    unrealized_pnl: float
    fees: float
    currency: str
    event_time_us: int
    def __init__(self, wallet_address: _Optional[str] = ..., chain: _Optional[str] = ..., symbol: _Optional[str] = ..., pnl_type: _Optional[_Union[PnLType, str]] = ..., realized_pnl: _Optional[float] = ..., unrealized_pnl: _Optional[float] = ..., fees: _Optional[float] = ..., currency: _Optional[str] = ..., event_time_us: _Optional[int] = ...) -> None: ...

class ServiceHeartbeat(_message.Message):
    __slots__ = ("service_name", "timestamp_us", "cpu_usage", "memory_mb", "messages_processed")
    SERVICE_NAME_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_US_FIELD_NUMBER: _ClassVar[int]
    CPU_USAGE_FIELD_NUMBER: _ClassVar[int]
    MEMORY_MB_FIELD_NUMBER: _ClassVar[int]
    MESSAGES_PROCESSED_FIELD_NUMBER: _ClassVar[int]
    service_name: str
    timestamp_us: int
    cpu_usage: float
    memory_mb: float
    messages_processed: int
    def __init__(self, service_name: _Optional[str] = ..., timestamp_us: _Optional[int] = ..., cpu_usage: _Optional[float] = ..., memory_mb: _Optional[float] = ..., messages_processed: _Optional[int] = ...) -> None: ...

class ControlCommand(_message.Message):
    __slots__ = ("command_id", "type", "target_symbol", "payload", "issued_at_us")
    COMMAND_ID_FIELD_NUMBER: _ClassVar[int]
    TYPE_FIELD_NUMBER: _ClassVar[int]
    TARGET_SYMBOL_FIELD_NUMBER: _ClassVar[int]
    PAYLOAD_FIELD_NUMBER: _ClassVar[int]
    ISSUED_AT_US_FIELD_NUMBER: _ClassVar[int]
    command_id: str
    type: CommandType
    target_symbol: str
    payload: bytes
    issued_at_us: int
    def __init__(self, command_id: _Optional[str] = ..., type: _Optional[_Union[CommandType, str]] = ..., target_symbol: _Optional[str] = ..., payload: _Optional[bytes] = ..., issued_at_us: _Optional[int] = ...) -> None: ...
